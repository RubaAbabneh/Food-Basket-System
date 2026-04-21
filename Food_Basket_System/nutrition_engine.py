"""
nutrition_engine.py
Core calculation engine with age-based food restrictions + WHO/FAO international constraints
BMR (Schofield) + PAL + LP Optimizer (scipy HiGHS)

Merged from two versions:
  v1 — WHO/FAO macro constraints (fiber, sodium, AMDR)
  v2 — Age-based food caps (FOOD_AGE_CAPS, GENERAL_CAPS_PER_PERSON, GROUP_DISPLAY_ORDER)
"""

import sqlite3
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from dataclasses import dataclass
from typing import Optional
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database", "nutrition.db")


# ══════════════════════════════════════════════════════════════════════════════
# AGE-BASED FOOD RESTRICTIONS
# Source: WHO/UNICEF/FAO feeding guidelines
# Max grams per person per day by age group
# ══════════════════════════════════════════════════════════════════════════════

def get_age_group(age: int) -> str:
    if age <= 2:  return 'infant'   # 0–24 months
    if age <= 9:  return 'child'    # 3–9 years
    if age <= 17: return 'teen'     # 10–17 years
    return 'adult'                  # 18+


# food_code → {age_group: max_g_per_person_per_day}
# 0 = completely forbidden for that age group
FOOD_AGE_CAPS = {
    # ── Infant/baby foods ── ONLY for infants, zero for everyone else
    '11116': {'infant': 50,  'child': 0,   'teen': 0,   'adult': 0  },  # سيريلاك
    '11405': {'infant': 200, 'child': 0,   'teen': 0,   'adult': 0  },  # حليب أطفال بودرة

    # ── Honey: FORBIDDEN for infants < 12m (botulism) ──
    '11804': {'infant': 0,   'child': 10,  'teen': 20,  'adult': 30 },  # عسل

    # ── High-sodium / processed snacks ──
    '11119': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 50 },  # شبس
    '11210': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 50 },  # مرتديلا
    '11209': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 50 },  # لحوم معلبة
    '11904': {'infant': 0,   'child': 2,   'teen': 3,   'adult': 5  },  # ملح
    '11912': {'infant': 0,   'child': 10,  'teen': 15,  'adult': 20 },  # كاتشاب
    '11916': {'infant': 0,   'child': 10,  'teen': 15,  'adult': 20 },  # مايونيز

    # ── Sugars & sweets ── WHO limit: <10% energy = ~50g/day for adult
    '11801': {'infant': 0,   'child': 15,  'teen': 25,  'adult': 50 },  # سكر
    '11802': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 50 },  # حلاوة طحينية
    '11803': {'infant': 0,   'child': 15,  'teen': 20,  'adult': 30 },  # مربى/دبس
    '11805': {'infant': 0,   'child': 30,  'teen': 50,  'adult': 80 },  # كنافة
    '11806': {'infant': 0,   'child': 30,  'teen': 50,  'adult': 80 },  # حلويات عربية
    '11807': {'infant': 0,   'child': 40,  'teen': 60,  'adult': 80 },  # كيك
    '11809': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 50 },  # شوكولاتة
    '11812': {'infant': 0,   'child': 60,  'teen': 80,  'adult': 100},  # آيس كريم
    '11808': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 50 },  # ملبس/توفي
    '11113': {'infant': 0,   'child': 30,  'teen': 50,  'adult': 80 },  # كعك
    '11114': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 50 },  # بسكويت

    # ── Beverages ── WHO: limit sugary drinks
    '12202': {'infant': 0,   'child': 0,   'teen': 100, 'adult': 200},  # مشروبات غازية
    '12204': {'infant': 0,   'child': 30,  'teen': 50,  'adult': 100},  # عصير مركز
    '12205': {'infant': 0,   'child': 30,  'teen': 50,  'adult': 100},  # عصائر بودرة
    '12101': {'infant': 0,   'child': 0,   'teen': 100, 'adult': 300},  # شاي
    '12102': {'infant': 0,   'child': 0,   'teen': 50,  'adult': 200},  # قهوة
    '12103': {'infant': 0,   'child': 0,   'teen': 50,  'adult': 200},  # نسكافيه

    # ── Raw flour / starch ──
    '11115': {'infant': 0,   'child': 10,  'teen': 20,  'adult': 30 },  # نشا

    # ── Cereals: reasonable daily servings ──
    '11118': {'infant': 0,   'child': 40,  'teen': 60,  'adult': 80 },  # كورن فليكس
    '11120': {'infant': 0,   'child': 20,  'teen': 30,  'adult': 40 },  # بوشار
    '11117': {'infant': 0,   'child': 50,  'teen': 80,  'adult': 100},  # قطايف
}


# ══════════════════════════════════════════════════════════════════════════════
# GENERAL SERVING CAPS (no age restriction, but physical upper limit)
# Max grams per person per day regardless of age
# ══════════════════════════════════════════════════════════════════════════════
GENERAL_CAPS_PER_PERSON = {
    # Cereals
    '11102': 400, '11103': 400, '11104': 200, '11105': 350,
    '11106': 350, '11107': 350, '11108': 300, '11109': 250,
    '11110': 200, '11111': 350,
    # Meat/fish
    '11201': 200, '11202': 200, '11203': 200, '11204': 200,
    '11205': 200, '11206': 150, '11207': 200, '11208': 250,
    '11211': 250, '11212': 250, '11213': 150,
    '11301': 200, '11302': 200, '11303': 200,
    # Dairy
    '11401': 500, '11402': 500, '11403': 100, '11404': 50,
    '11406': 300, '11407': 300, '11408': 200, '11410': 150,
    '11411': 100, '11412': 80,  '11413': 80,  '11415': 80,
    '11417': 50,  '11418': 30,  '11419': 30,  '11420': 30,
    '11421': 20,  '11422': 150,
    # Fats/oils: WHO max ~35% energy ≈ 80g/day for adult
    '11501': 40,  '11502': 40,  '11503': 40,  '11504': 30,
    # Fruits
    '11601': 200, '11602': 150, '11603': 100, '11604': 150,
    '11605': 200, '11606': 200, '11607': 200, '11608': 300,
    '11609': 250, '11610': 150, '11611': 150, '11612': 150,
    '11613': 150, '11614': 150, '11615': 100, '11616': 100,
    '11617': 150, '11619': 150, '11620': 200, '11621': 200,
    '11622': 100, '11623': 50,  '11624': 30,  '11625': 50,
    '11627': 50,  '11628': 50,  '11629': 30,
    # Vegetables: WHO recommends 400g/day total
    '11701': 250, '11702': 300, '11703': 100, '11704': 30,
    '11705': 200, '11706': 200, '11707': 200, '11708': 150,
    '11709': 150, '11710': 200, '11711': 150, '11712': 200,
    '11713': 200, '11714': 200, '11715': 200, '11716': 200,
    '11717': 200, '11718': 200, '11719': 150, '11720': 60,
    '11721': 100, '11722': 80,  '11723': 300,
    # Legumes
    '11724': 200, '11725': 150, '11726': 200,
    # Spices/condiments
    '11901': 3,   '11902': 5,   '11903': 3,   '11905': 20,
    '11907': 50,  '11908': 40,  '11909': 80,  '11914': 10,
    '12104': 30,  '12201': 500, '12203': 200,
}


# ══════════════════════════════════════════════════════════════════════════════
# GROUP ORDER for display (FAO food plate sequence)
# ══════════════════════════════════════════════════════════════════════════════
GROUP_DISPLAY_ORDER = {1: 1, 5: 2, 4: 3, 2: 4, 3: 5, 6: 6, 7: 7, 8: 8}


# ══════════════════════════════════════════════════════════════════════════════
# BMR — Schofield Equations (WHO/FAO 1985)
# ══════════════════════════════════════════════════════════════════════════════
def calculate_bmr(age: int, gender: str, weight_kg: float, height_cm: float) -> float:
    g = gender.lower()
    h = height_cm / 100
    if age < 3:
        return (0.249*weight_kg - 0.127)*239 if g=='male' else (0.244*weight_kg - 0.130)*239
    elif age <= 10:
        return (0.095*weight_kg + 2.110*h + 0.166)*239 if g=='male' else (0.085*weight_kg + 2.033*h - 0.651)*239
    elif age <= 18:
        return (0.074*weight_kg + 2.754*h + 0.082)*239 if g=='male' else (0.056*weight_kg + 1.938*h + 0.129)*239
    elif age <= 30:
        return (0.063*weight_kg + 2.896*h - 3.108)*239 if g=='male' else (0.062*weight_kg + 2.036*h + 0.069)*239
    elif age <= 60:
        return (0.048*weight_kg + 3.122*h - 3.338)*239 if g=='male' else (0.034*weight_kg + 2.882*h - 1.290)*239
    else:
        return (0.049*weight_kg + 2.459*h - 1.840)*239 if g=='male' else (0.038*weight_kg + 2.755*h - 1.320)*239


def calculate_tdee(bmr: float, pal_value: float) -> float:
    """حساب إجمالي الطاقة اليومية المصروفة (TDEE) = BMR × PAL"""
    return bmr * pal_value


def get_requirements(age: int, gender: str) -> Optional[dict]:
    """تحديد الاحتياجات الغذائية الدنيا والعليا من قاعدة البيانات"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""SELECT * FROM nutritional_requirements
                 WHERE age_min<=? AND age_max>=? AND (gender=? OR gender='both')
                 AND life_stage='normal'
                 ORDER BY ABS(age_min-?) LIMIT 1""", (age, age, gender, age))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_special_addition(life_stage: str) -> Optional[dict]:
    """إضافات غذائية للحالات الخاصة كالحمل والرضاعة"""
    if life_stage == 'normal':
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM special_requirements WHERE life_stage=?", (life_stage,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_pal(pal_level: str) -> float:
    """جلب قيمة PAL من قاعدة البيانات مع fallback للقيم الافتراضية"""
    pal_map = {'sedentary':1.40,'light':1.55,'moderate':1.75,'active':2.00,'very_active':2.20}
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT pal_value FROM pal_values WHERE pal_level=?", (pal_level,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else pal_map.get(pal_level, 1.55)


# ══════════════════════════════════════════════════════════════════════════════
# Person dataclass
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class Person:
    name: str
    age: int
    gender: str
    weight_kg: float
    height_cm: float
    pal_level: str
    life_stage: str = 'normal'

    @property
    def bmr(self): return calculate_bmr(self.age, self.gender, self.weight_kg, self.height_cm)
    @property
    def pal_value(self): return get_pal(self.pal_level)
    @property
    def tdee(self): return calculate_tdee(self.bmr, self.pal_value)
    @property
    def age_group(self): return get_age_group(self.age)  # infant/child/teen/adult

    def get_requirements(self) -> dict:
        base = get_requirements(self.age, self.gender)
        if not base:
            return {}
        base = dict(base)
        special = get_special_addition(self.life_stage)
        if special:
            for key, extra_key in [
                ('energy_kcal_min','extra_energy_kcal'),('protein_g_min','extra_protein_g'),
                ('vit_a_ug_min','extra_vit_a_ug'),('vit_d_ug_min','extra_vit_d_ug'),
                ('vit_c_mg_min','extra_vit_c_mg'),('vit_b1_mg_min','extra_vit_b1_mg'),
                ('vit_b2_mg_min','extra_vit_b2_mg'),('vit_b6_mg_min','extra_vit_b6_mg'),
                ('vit_b12_ug_min','extra_vit_b12_ug'),('folate_ug_min','extra_folate_ug'),
                ('calcium_mg_min','extra_calcium_mg'),('iron_mg_min','extra_iron_mg'),
                ('zinc_mg_min','extra_zinc_mg'),('iodine_ug_min','extra_iodine_ug'),
                ('magnesium_mg_min','extra_magnesium_mg'),('selenium_ug_min','extra_selenium_ug'),
            ]:
                base[key] = (base.get(key) or 0) + (special.get(extra_key) or 0)
        base['energy_kcal_min'] = self.tdee
        return base


# ══════════════════════════════════════════════════════════════════════════════
# NUTRIENT DEFINITIONS
# fiber_g و sodium_mg مضافان لتتبعهما في النتائج وتطبيق قيود WHO/FAO
# ══════════════════════════════════════════════════════════════════════════════
NUTRIENT_COLS = [
    'energy_kcal','protein_g','vit_a_ug','vit_c_mg','vit_d_ug',
    'calcium_mg','iron_mg','zinc_mg','folate_ug','vit_b12_ug',
    'fat_g','carb_g','fiber_g','sodium_mg'
]

NUTRIENT_REQ_MAP = {
    'energy_kcal':('energy_kcal_min','energy_kcal_max'),
    'protein_g':  ('protein_g_min',  'protein_g_max'),
    'vit_a_ug':   ('vit_a_ug_min',   'vit_a_ug_max'),
    'vit_c_mg':   ('vit_c_mg_min',   'vit_c_mg_max'),
    'vit_d_ug':   ('vit_d_ug_min',   'vit_d_ug_max'),
    'calcium_mg': ('calcium_mg_min', 'calcium_mg_max'),
    'iron_mg':    ('iron_mg_min',    'iron_mg_max'),
    'zinc_mg':    ('zinc_mg_min',    'zinc_mg_max'),
    'folate_ug':  ('folate_ug_min',  'folate_ug_max'),
    'vit_b12_ug': ('vit_b12_ug_min', 'vit_b12_ug_max'),
}


def _aggregate_requirements(persons: list) -> dict:
    """تجميع الاحتياجات الغذائية لجميع أفراد الأسرة"""
    agg = {}
    for person in persons:
        for k, v in person.get_requirements().items():
            if v is not None and isinstance(v, (int, float)):
                agg[k] = (agg.get(k) or 0) + v
    return agg


def _calc_food_bounds(food_code: str, persons: list) -> tuple:
    """
    حساب الحد الأدنى والأقصى (بوحدات 100g/يوم) لغذاء معين
    بناءً على تركيبة الأسرة العمرية.
    الأولوية: FOOD_AGE_CAPS ← GENERAL_CAPS_PER_PERSON ← افتراضي 500g/شخص
    """
    age_caps = FOOD_AGE_CAPS.get(food_code)
    gen_cap  = GENERAL_CAPS_PER_PERSON.get(food_code)

    if age_caps is not None:
        total_max_g = sum(age_caps.get(p.age_group, 0) for p in persons)
    elif gen_cap is not None:
        total_max_g = gen_cap * len(persons)
    else:
        total_max_g = 500 * len(persons)

    return (0, total_max_g / 100)   # تحويل إلى وحدات 100g


# ══════════════════════════════════════════════════════════════════════════════
# BASKET OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════
def optimize_basket(persons: list, price_df, n_days: int = 30) -> dict:
    """
    محسّن البرمجة الخطية باستخدام scipy HiGHS.
    x[i] = وحدات 100g من الغذاء i يومياً (إجمالي الأسرة).

    القيود المطبّقة:
      1. الاحتياجات الغذائية الدنيا والعليا (NUTRIENT_REQ_MAP)
      2. قيود WHO/FAO الدولية: ألياف، صوديوم، AMDR (دهون/كربوهيدرات)
      3. تنوع مجموعات الغذاء: ≥10g/شخص/يوم من كل مجموعة
      4. حدود الأغذية الفردية مراعيةً للعمر (_calc_food_bounds)
    """
    conn = sqlite3.connect(DB_PATH)
    foods_df = pd.read_sql("""
        SELECT fc.*, fg.group_name_ar, fg.group_name, fg.id AS group_id_fk
        FROM food_composition fc
        LEFT JOIN food_groups fg ON fc.food_group_id = fg.id
    """, conn)
    conn.close()

    # ── تنظيف ملف الأسعار ──────────────────────────────────────────────────
    price_df = price_df.copy()
    price_df.columns = [str(c).lower().strip() for c in price_df.columns]
    if 'food_code' not in price_df.columns:
        if len(price_df.columns) >= 2:
            cols = list(price_df.columns)
            cols[0], cols[1] = 'food_code', 'price_per_100g'
            price_df.columns = cols
        else:
            return {"error": "ملف الأسعار يجب أن يحتوي على عمودي: food_code و price_per_100g"}

    price_df['food_code'] = price_df['food_code'].astype(str).str.strip()
    price_df['price_per_100g'] = pd.to_numeric(price_df['price_per_100g'], errors='coerce').fillna(0)
    price_df = price_df[price_df['price_per_100g'] > 0]

    merged = foods_df.merge(
        price_df[['food_code','price_per_100g']], on='food_code', how='inner'
    ).reset_index(drop=True)

    if merged.empty:
        return {"error": "لم يتم العثور على أغذية مطابقة بين قاعدة البيانات وملف الأسعار. تحقق من أكواد الأغذية."}

    total_reqs = _aggregate_requirements(persons)
    n_persons  = len(persons)

    # ── دالة الهدف: تقليل التكلفة الإجمالية ───────────────────────────────
    c_obj = merged['price_per_100g'].values.astype(float) * n_days

    # ── قيود عدم المساواة (A_ub @ x <= b_ub) ──────────────────────────────
    A_ub_rows, b_ub_rows = [], []

    # 1. القيود الغذائية الأساسية (دنيا وعليا)
    for nut_col, (min_key, max_key) in NUTRIENT_REQ_MAP.items():
        if nut_col not in merged.columns:
            continue
        nut_vals = merged[nut_col].fillna(0).values.astype(float)
        req_min  = total_reqs.get(min_key) or 0
        if req_min > 0:
            A_ub_rows.append(-nut_vals)
            b_ub_rows.append(-req_min)
        req_max = total_reqs.get(max_key)
        if req_max and req_max > 0 and req_max > req_min:
            A_ub_rows.append(nut_vals)
            b_ub_rows.append(req_max)

    # ──────────────────────────────────────────────────────────────────────
    # 2. القيود الدولية الإضافية (WHO/FAO)
    # ──────────────────────────────────────────────────────────────────────
    total_energy_min = total_reqs.get('energy_kcal_min', 0)

    if total_energy_min > 0:
        # الألياف (Fiber): ≥ 25g/شخص/يوم
        if 'fiber_g' in merged.columns:
            fiber_vals = merged['fiber_g'].fillna(0).values.astype(float)
            A_ub_rows.append(-fiber_vals)
            b_ub_rows.append(-(25 * n_persons))

        # الصوديوم (Sodium): ≤ 2000mg/شخص/يوم
        if 'sodium_mg' in merged.columns:
            sodium_vals = merged['sodium_mg'].fillna(0).values.astype(float)
            A_ub_rows.append(sodium_vals)
            b_ub_rows.append(2000 * n_persons)

        # AMDR — الدهون: ≤ 30% من السعرات (1g دهن = 9 kcal)
        if 'fat_g' in merged.columns:
            fat_vals = merged['fat_g'].fillna(0).values.astype(float)
            A_ub_rows.append(9 * fat_vals)
            b_ub_rows.append(0.30 * total_energy_min)

        # AMDR — الكربوهيدرات: 45%–65% من السعرات (1g كربوهيدرات = 4 kcal)
        if 'carb_g' in merged.columns:
            carb_vals = merged['carb_g'].fillna(0).values.astype(float)
            A_ub_rows.append(4 * carb_vals)
            b_ub_rows.append(0.65 * total_energy_min)
            A_ub_rows.append(-(4 * carb_vals))
            b_ub_rows.append(-(0.45 * total_energy_min))

    # 3. تنوع مجموعات الغذاء: ≥ 10g/شخص/يوم من كل مجموعة
    #    (مع استثناء مجموعة التوابل/المشروبات)
    for gname in merged['group_name'].dropna().unique():
        if gname in ('spices_bev',):
            continue
        mask = (merged['group_name'] == gname).values.astype(float)
        if mask.sum() > 0:
            A_ub_rows.append(-mask)
            b_ub_rows.append(-0.1 * n_persons)

    A_ub = np.array(A_ub_rows, dtype=float)
    b_ub = np.array(b_ub_rows, dtype=float)

    # ── الحدود: مراعاة العمر لكل غذاء ─────────────────────────────────────
    bounds = [
        _calc_food_bounds(str(row['food_code']), persons)
        for _, row in merged.iterrows()
    ]

    # ── الحل ───────────────────────────────────────────────────────────────
    res = linprog(c_obj, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method='highs')

    if res.status not in (0, 1):
        msgs = {
            2: "المسألة غير قابلة للحل — تأكد من وجود أغذية متنوعة في ملف الأسعار",
            3: "المسألة غير محدودة",
            4: "خطأ عددي في الحل",
        }
        return {"error": msgs.get(res.status, f"لم يُوجد حل: {res.message}")}

    x = res.x

    # ── بناء النتيجة ────────────────────────────────────────────────────────
    basket_items    = []
    total_cost      = 0.0
    total_nutrients = {k: 0.0 for k in NUTRIENT_COLS}

    for i, row in merged.iterrows():
        qty = float(x[i]) if x[i] > 0.005 else 0.0
        if qty < 0.005:
            continue
        item_cost   = qty * float(row['price_per_100g']) * n_days
        total_cost += item_cost

        basket_items.append({
            'food_code':     row['food_code'],
            'food_name_ar':  row['food_name_ar'],
            'food_name_en':  row.get('food_name_en', ''),
            'group_name_ar': row.get('group_name_ar', ''),
            'group_name':    row.get('group_name', ''),
            'food_group_id': int(row.get('food_group_id', 0) or 0),
            'qty_g_per_day': round(qty * 100, 1),
            'qty_g_total':   round(qty * 100 * n_days, 1),
            'price_per_100g':float(row['price_per_100g']),
            'item_cost':     round(item_cost, 3),
        })

        for k in NUTRIENT_COLS:
            if k in merged.columns:
                total_nutrients[k] += qty * float(row.get(k, 0) or 0)

    # ── الترتيب: حسب GROUP_DISPLAY_ORDER ثم التكلفة تنازلياً ──────────────
    basket_items.sort(key=lambda it: (
        GROUP_DISPLAY_ORDER.get(it['food_group_id'], 99),
        -it['item_cost']
    ))

    # ── تحليل التغطية الغذائية ─────────────────────────────────────────────
    coverage = {}
    for nut_col, (min_key, max_key) in NUTRIENT_REQ_MAP.items():
        daily   = total_nutrients.get(nut_col, 0)
        req_min = total_reqs.get(min_key, 0) or 0
        req_max = total_reqs.get(max_key)
        pct     = (daily / req_min * 100) if req_min > 0 else 100.0
        coverage[nut_col] = {
            'value':        round(daily, 2),
            'required_min': round(req_min, 2),
            'required_max': round(req_max, 2) if req_max else None,
            'coverage_pct': round(min(pct, 200), 1),
            'status':       'ok' if daily >= req_min * 0.95 else 'deficit',
        }

    return {
        'status':             'success',
        'basket_items':       basket_items,
        'total_cost':         round(total_cost, 3),
        'total_cost_per_day': round(total_cost / n_days, 3),
        'n_days':             n_days,
        'n_persons':          n_persons,
        'coverage':           coverage,
        'total_requirements': {k: round(v, 2) if v else v
                               for k, v in total_reqs.items() if v is not None},
    }

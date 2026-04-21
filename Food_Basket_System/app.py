"""
app.py — نظام السلة الغذائية الأردنية
دعم اختيار المحافظة من ملف أسعار متعدد المحافظات
"""

import os, io, json
import pandas as pd
from flask import Flask, render_template, request, jsonify, session, send_file
from werkzeug.utils import secure_filename
from database.init_db import init_database, get_connection
from nutrition_engine import Person, optimize_basket

app = Flask(__name__)
app.secret_key = "jordan_food_basket_2024_secret"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

JORDAN_GOVERNORATES = [
    'عمان','البلقاء','الزرقاء','مادبا',
    'اربد','المغرق','جرش','عجلون',
    'الكرك','الطفيلة','معان','العقبة'
]

init_database()


def allowed_file(f): return '.' in f and f.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS
def _read_df(fp): return pd.read_csv(fp) if fp.endswith('.csv') else pd.read_excel(fp)

def _detect_type(df):
    cols = [str(c).strip() for c in df.columns]
    found = [c for c in cols if c in JORDAN_GOVERNORATES]
    if len(found) >= 2: return 'multi_gov', found
    if any('price_per_100g' in c.lower() for c in cols): return 'single', []
    return 'multi_gov', cols[3:]


@app.route('/')
def index(): return render_template('index.html')


@app.route('/upload_prices', methods=['POST'])
def upload_prices():
    if 'price_file' not in request.files:
        return jsonify({'error': 'لم يتم رفع أي ملف'}), 400
    file = request.files['price_file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'صيغة الملف غير مدعومة'}), 400

    fn = secure_filename(file.filename)
    fp = os.path.join(app.config['UPLOAD_FOLDER'], fn)
    file.save(fp)

    try:
        df = _read_df(fp)
        df.columns = [str(c).strip() for c in df.columns]
        ftype, gov_cols = _detect_type(df)
        code_col = df.columns[0]
        df[code_col] = df[code_col].astype(str).str.strip()
        df = df[df[code_col].str.match(r'^\d{5}$')]

        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT food_code, food_name_ar FROM food_composition")
        db_foods = {r['food_code']: r['food_name_ar'] for r in c.fetchall()}
        conn.close()

        if ftype == 'multi_gov':
            for gc in gov_cols:
                df[gc] = pd.to_numeric(df[gc], errors='coerce').fillna(0)

            # Auto-detect unit: if median price > 10 → assumes fils/kg → convert to JOD/100g
            display_gov = gov_cols[0]
            median_price = df[display_gov][df[display_gov] > 0].median()
            price_factor = 1.0
            if pd.notna(median_price) and median_price > 10:
                price_factor = 1.0 / 10000   # fils/kg → JOD/100g
                for gc in gov_cols:
                    df[gc] = df[gc] * price_factor

            display_gov = gov_cols[0]
            matched = df[df[code_col].isin(db_foods)].copy()
            matched_list = [
                {'food_code': r[code_col], 'food_name_ar': db_foods.get(r[code_col],''),
                 'price_display': round(float(r[display_gov]),4)}
                for _, r in matched.iterrows() if float(r[display_gov]) > 0
            ]
            return jsonify({
                'success': True, 'file_type': 'multi_gov',
                'governorates': gov_cols, 'filepath': fp,
                'total_rows': len(df), 'matched': len(matched_list),
                'matched_foods': matched_list,
                'message': f'✅ ملف متعدد المحافظات — {len(gov_cols)} محافظة — {len(matched_list)} غذاء'
            })
        else:
            cols_l = {c.lower(): c for c in df.columns}
            pc = cols_l.get('price_per_100g', df.columns[1])
            df[pc] = pd.to_numeric(df[pc], errors='coerce').fillna(0)
            matched = df[df[code_col].isin(db_foods) & (df[pc]>0)]
            matched_list = [
                {'food_code': r[code_col], 'food_name_ar': db_foods.get(r[code_col],''),
                 'price_display': round(float(r[pc]),4)}
                for _, r in matched.iterrows()
            ]
            return jsonify({
                'success': True, 'file_type': 'single', 'governorates': [],
                'filepath': fp, 'total_rows': len(df), 'matched': len(matched_list),
                'matched_foods': matched_list,
                'message': f'✅ ملف أسعار موحد — {len(matched_list)} غذاء'
            })
    except Exception as e:
        return jsonify({'error': f'خطأ في قراءة الملف: {e}'}), 400


@app.route('/api/governorate_preview', methods=['POST'])
def governorate_preview():
    data = request.get_json()
    fp, gov = data.get('filepath',''), data.get('governorate','')
    if not fp or not os.path.exists(fp): return jsonify({'error': 'ملف غير موجود'}), 400
    try:
        df = _read_df(fp); df.columns = [str(c).strip() for c in df.columns]
        code_col = df.columns[0]
        df[code_col] = df[code_col].astype(str).str.strip()
        df = df[df[code_col].str.match(r'^\d{5}$')]
        if gov not in df.columns: return jsonify({'error': f'المحافظة "{gov}" غير موجودة'}), 400
        conn = get_connection(); c = conn.cursor()
        c.execute("SELECT food_code, food_name_ar FROM food_composition")
        db_foods = {r['food_code']: r['food_name_ar'] for r in c.fetchall()}; conn.close()
        # Auto-convert fils/kg → JOD/100g if needed
        df[gov] = pd.to_numeric(df[gov], errors='coerce').fillna(0)
        med_p = df.loc[df[gov]>0, gov].median()
        factor = 1/10000 if (pd.notna(med_p) and med_p > 10) else 1.0
        items = [
            {'food_code': r[code_col], 'food_name_ar': db_foods.get(r[code_col],''),
             'price': round(float(r[gov]) * factor, 4)}
            for _, r in df.iterrows()
            if r[code_col] in db_foods and float(r[gov]) > 0
        ]
        return jsonify({'governorate': gov, 'items': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/calculate', methods=['POST'])
def calculate():
    data = request.get_json()
    if not data: return jsonify({'error': 'لم يتم إرسال بيانات'}), 400
    persons_data = data.get('persons', [])
    n_days = int(data.get('n_days', 30))
    fp     = data.get('prices_file', '')
    gov    = data.get('governorate', '')
    ftype  = data.get('file_type', 'single')
    if not persons_data: return jsonify({'error': 'أدخل بيانات شخص واحد على الأقل'}), 400
    if not fp or not os.path.exists(fp): return jsonify({'error': 'يرجى رفع ملف الأسعار أولاً'}), 400

    try:
        df = _read_df(fp); df.columns = [str(c).strip() for c in df.columns]
        code_col = df.columns[0]
        df[code_col] = df[code_col].astype(str).str.strip()
        df = df[df[code_col].str.match(r'^\d{5}$')]

        if ftype == 'multi_gov':
            if not gov: return jsonify({'error': 'يرجى اختيار المحافظة'}), 400
            if gov not in df.columns: return jsonify({'error': f'المحافظة "{gov}" غير موجودة'}), 400
            price_df = df[[code_col, gov]].copy()
            price_df.columns = ['food_code', 'price_per_100g']
            # Auto-convert fils/kg → JOD/100g if needed
            price_df['price_per_100g'] = pd.to_numeric(price_df['price_per_100g'], errors='coerce').fillna(0)
            med = price_df.loc[price_df['price_per_100g']>0, 'price_per_100g'].median()
            if pd.notna(med) and med > 10:
                price_df['price_per_100g'] = price_df['price_per_100g'] / 10000
        else:
            cols_l = {c.lower(): c for c in df.columns}
            pc = cols_l.get('price_per_100g', df.columns[1])
            price_df = df[[code_col, pc]].copy()
            price_df.columns = ['food_code', 'price_per_100g']

        price_df['food_code'] = price_df['food_code'].astype(str).str.strip()
        price_df['price_per_100g'] = pd.to_numeric(price_df['price_per_100g'], errors='coerce').fillna(0)
        price_df = price_df[price_df['price_per_100g'] > 0]
    except Exception as e:
        return jsonify({'error': f'خطأ في تحميل الأسعار: {e}'}), 400

    persons, summaries = [], []
    for pi in persons_data:
        try:
            p = Person(
                name=pi.get('name','فرد'), age=int(pi['age']), gender=pi['gender'],
                weight_kg=float(pi['weight_kg']), height_cm=float(pi['height_cm']),
                pal_level=pi.get('pal_level','moderate'), life_stage=pi.get('life_stage','normal')
            )
            persons.append(p)
            summaries.append({
                'name': p.name, 'age': p.age,
                'gender': 'ذكر' if p.gender=='male' else 'أنثى',
                'weight_kg': p.weight_kg, 'height_cm': p.height_cm,
                'bmr': round(p.bmr,1), 'pal_value': p.pal_value,
                'tdee': round(p.tdee,1), 'life_stage': pi.get('life_stage','normal')
            })
        except Exception as e:
            return jsonify({'error': f'خطأ في بيانات الفرد: {e}'}), 400

    result = optimize_basket(persons, price_df, n_days)
    if 'error' in result: return jsonify({'error': result['error']}), 400
    result['persons'] = summaries
    result['governorate'] = gov or 'غير محدد'
    return jsonify(result)


@app.route('/api/foods')
def api_foods():
    conn = get_connection(); c = conn.cursor()
    c.execute("""SELECT fc.food_code,fc.food_name_ar,fc.food_name_en,
                        fg.group_name_ar,fc.energy_kcal,fc.protein_g,fc.fat_g,fc.carb_g
                 FROM food_composition fc
                 LEFT JOIN food_groups fg ON fc.food_group_id=fg.id
                 ORDER BY fg.group_name_ar,fc.food_name_ar""")
    foods = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(foods)

@app.route('/api/pal_values')
def api_pal():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM pal_values")
    r = [dict(x) for x in c.fetchall()]; conn.close(); return jsonify(r)

@app.route('/api/food_groups')
def api_food_groups():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT * FROM food_groups")
    r = [dict(x) for x in c.fetchall()]; conn.close(); return jsonify(r)

@app.route('/api/governorates')
def api_governorates():
    return jsonify(JORDAN_GOVERNORATES)


@app.route('/template_prices')
def template_prices():
    conn = get_connection(); c = conn.cursor()
    c.execute("SELECT food_code,food_name_ar,food_name_en FROM food_composition ORDER BY food_code")
    foods = c.fetchall(); conn.close()
    buf = io.BytesIO()
    rows = [{'food_code': f['food_code'], 'food_name_ar': f['food_name_ar'],
             'food_name_en': f['food_name_en'], **{g: 0.0 for g in JORDAN_GOVERNORATES}}
            for f in foods]
    pd.DataFrame(rows).to_excel(buf, index=False)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name='نموذج_أسعار_المحافظات.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
    print("🌿 نظام السلة الغذائية الأردنية")
    print("🌐 http://127.0.0.1:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)

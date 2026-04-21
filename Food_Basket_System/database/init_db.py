"""
database/init_db.py
Initialize SQLite database with all nutritional science tables
"""

import sqlite3
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DB_PATH = os.path.join(os.path.dirname(__file__), "nutrition.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_connection()
    c = conn.cursor()

    # ============================================================
    # TABLE 1: Nutritional Requirements by Age/Gender
    # ============================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS nutritional_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        age_min INTEGER NOT NULL,
        age_max INTEGER NOT NULL,
        gender TEXT NOT NULL CHECK(gender IN ('male','female','both')),
        life_stage TEXT DEFAULT 'normal',

        -- Energy (kcal/day) - calculated via BMR*PAL but we store reference values
        energy_kcal_min REAL,
        energy_kcal_max REAL,

        -- Macronutrients
        protein_g_min REAL,
        protein_g_max REAL,
        fat_pct_min REAL,
        fat_pct_max REAL,
        carb_pct_min REAL,
        carb_pct_max REAL,
        fiber_g_min REAL,

        -- Fat-soluble vitamins
        vit_a_ug_min REAL,   vit_a_ug_max REAL,
        vit_d_ug_min REAL,   vit_d_ug_max REAL,
        vit_e_mg_min REAL,   vit_e_mg_max REAL,
        vit_k_ug_min REAL,   vit_k_ug_max REAL,

        -- Water-soluble vitamins
        vit_c_mg_min REAL,   vit_c_mg_max REAL,
        vit_b1_mg_min REAL,  vit_b1_mg_max REAL,
        vit_b2_mg_min REAL,  vit_b2_mg_max REAL,
        vit_b3_mg_min REAL,  vit_b3_mg_max REAL,
        vit_b6_mg_min REAL,  vit_b6_mg_max REAL,
        vit_b12_ug_min REAL, vit_b12_ug_max REAL,
        folate_ug_min REAL,  folate_ug_max REAL,

        -- Minerals
        calcium_mg_min REAL,  calcium_mg_max REAL,
        iron_mg_min REAL,     iron_mg_max REAL,
        zinc_mg_min REAL,     zinc_mg_max REAL,
        iodine_ug_min REAL,   iodine_ug_max REAL,
        magnesium_mg_min REAL,magnesium_mg_max REAL,
        phosphorus_mg_min REAL,phosphorus_mg_max REAL,
        potassium_mg_min REAL, potassium_mg_max REAL,
        sodium_mg_min REAL,    sodium_mg_max REAL,
        selenium_ug_min REAL,  selenium_ug_max REAL,

        -- BMR formula coefficients (Schofield equation)
        bmr_formula TEXT
    )
    """)

    # ============================================================
    # TABLE 2: Food Groups
    # ============================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS food_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_name TEXT NOT NULL,
        group_name_ar TEXT NOT NULL,
        recommended_pct_energy REAL,
        min_pct_energy REAL,
        max_pct_energy REAL,
        description_ar TEXT
    )
    """)

    # ============================================================
    # TABLE 3: Food Composition (per 100g)
    # ============================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS food_composition (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        food_code TEXT UNIQUE,
        food_name_ar TEXT NOT NULL,
        food_name_en TEXT,
        food_group_id INTEGER REFERENCES food_groups(id),
        energy_kcal REAL DEFAULT 0,
        protein_g REAL DEFAULT 0,
        fat_g REAL DEFAULT 0,
        carb_g REAL DEFAULT 0,
        fiber_g REAL DEFAULT 0,
        vit_a_ug REAL DEFAULT 0,
        vit_d_ug REAL DEFAULT 0,
        vit_e_mg REAL DEFAULT 0,
        vit_k_ug REAL DEFAULT 0,
        vit_c_mg REAL DEFAULT 0,
        vit_b1_mg REAL DEFAULT 0,
        vit_b2_mg REAL DEFAULT 0,
        vit_b3_mg REAL DEFAULT 0,
        vit_b6_mg REAL DEFAULT 0,
        vit_b12_ug REAL DEFAULT 0,
        folate_ug REAL DEFAULT 0,
        calcium_mg REAL DEFAULT 0,
        iron_mg REAL DEFAULT 0,
        zinc_mg REAL DEFAULT 0,
        iodine_ug REAL DEFAULT 0,
        magnesium_mg REAL DEFAULT 0,
        phosphorus_mg REAL DEFAULT 0,
        potassium_mg REAL DEFAULT 0,
        sodium_mg REAL DEFAULT 0,
        selenium_ug REAL DEFAULT 0
    )
    """)

    # ============================================================
    # TABLE 4: Pregnancy / Lactation / Infant Additional Needs
    # ============================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS special_requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        life_stage TEXT NOT NULL,  -- 'pregnant_t1','pregnant_t2','pregnant_t3','lactating','infant_0_6','infant_7_12'
        label_ar TEXT,

        -- Additional energy above normal
        extra_energy_kcal REAL DEFAULT 0,

        -- Macronutrients additions
        extra_protein_g REAL DEFAULT 0,
        extra_fat_g REAL DEFAULT 0,

        -- Vitamins additions
        extra_vit_a_ug REAL DEFAULT 0,
        extra_vit_d_ug REAL DEFAULT 0,
        extra_vit_c_mg REAL DEFAULT 0,
        extra_vit_b1_mg REAL DEFAULT 0,
        extra_vit_b2_mg REAL DEFAULT 0,
        extra_vit_b6_mg REAL DEFAULT 0,
        extra_vit_b12_ug REAL DEFAULT 0,
        extra_folate_ug REAL DEFAULT 0,

        -- Minerals additions
        extra_calcium_mg REAL DEFAULT 0,
        extra_iron_mg REAL DEFAULT 0,
        extra_zinc_mg REAL DEFAULT 0,
        extra_iodine_ug REAL DEFAULT 0,
        extra_magnesium_mg REAL DEFAULT 0,
        extra_selenium_ug REAL DEFAULT 0
    )
    """)

    # ============================================================
    # TABLE 5: PAL (Physical Activity Level) coefficients
    # ============================================================
    c.execute("""
    CREATE TABLE IF NOT EXISTS pal_values (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pal_level TEXT NOT NULL,
        pal_label_ar TEXT NOT NULL,
        pal_value REAL NOT NULL,
        description_ar TEXT
    )
    """)

    conn.commit()
    _seed_data(c)
    conn.commit()
    conn.close()
    print(f"✅ Database initialized at: {DB_PATH}")


def _seed_data(c):
    """Insert scientific reference data"""

    # --- PAL Values (WHO/FAO 2004) ---
    pal_data = [
        ("sedentary",    "خامل (جلوس معظم اليوم)",           1.40, "يجلس معظم اليوم، لا نشاط رياضي"),
        ("light",        "نشاط خفيف",                          1.55, "عمل مكتبي مع مشي خفيف"),
        ("moderate",     "نشاط معتدل",                         1.75, "يمشي أو يمارس الرياضة 3-5 أيام/أسبوع"),
        ("active",       "نشاط عالٍ",                          2.00, "رياضة يومية أو عمل جسدي"),
        ("very_active",  "نشاط مرتفع جداً",                    2.20, "رياضة شديدة + عمل جسدي مكثف"),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO pal_values(pal_level,pal_label_ar,pal_value,description_ar) VALUES(?,?,?,?)",
        pal_data
    )

    # --- Food Groups ---
    # Delete all and re-insert with fixed IDs (prevents duplicate seeding)
    c.execute("DELETE FROM food_groups")
    groups = [
        (1, "cereals",    "الحبوب والنشويات",              40, 35, 55, "خبز، أرز، معكرونة، بطاطا، حبوب"),
        (2, "vegetables", "الخضروات",                      15, 10, 20, "جميع أنواع الخضروات الطازجة والمجمدة"),
        (3, "fruits",     "الفواكه والمكسرات",             10,  8, 15, "جميع أنواع الفواكه الطازجة والمكسرات"),
        (4, "dairy",      "الألبان ومشتقاتها والبيض",     12, 10, 15, "حليب، لبن، جبنة، زبادي، بيض"),
        (5, "meat_fish",  "اللحوم والأسماك والبقوليات",   13, 10, 20, "لحوم، دواجن، أسماك، بيض، بقوليات"),
        (6, "fats_oils",  "الدهون والزيوت",                8,  5, 10, "زيوت نباتية، زبدة، سمنة"),
        (7, "sugars",     "السكريات والحلويات",             2,  0,  5, "سكر، عسل، مربى، حلويات"),
        (8, "spices_bev", "التوابل والمشروبات",             0,  0,  2, "توابل، مخللات، مشروبات، بهارات"),
    ]
    c.executemany(
        "INSERT INTO food_groups(id,group_name,group_name_ar,recommended_pct_energy,min_pct_energy,max_pct_energy,description_ar) VALUES(?,?,?,?,?,?,?)",
        groups
    )

    # --- Nutritional Requirements (WHO/FAO/UNHCR reference values) ---
    # Format: age_min, age_max, gender, life_stage,
    #         energy_min, energy_max,
    #         protein_min, protein_max, fat_pct_min, fat_pct_max, carb_pct_min, carb_pct_max, fiber,
    #         vit_a_min, vit_a_max, vit_d_min, vit_d_max, vit_e_min, vit_e_max, vit_k_min, vit_k_max,
    #         vit_c_min, vit_c_max, b1_min, b1_max, b2_min, b2_max, b3_min, b3_max, b6_min, b6_max, b12_min, b12_max, folate_min, folate_max,
    #         ca_min, ca_max, fe_min, fe_max, zn_min, zn_max, iodine_min, iodine_max, mg_min, mg_max, p_min, p_max, k_min, k_max, na_min, na_max, se_min, se_max,
    #         bmr_formula

    req_data = [
        # Infants 0-12 months
        (0, 0, 'both', 'infant', 550, 700,   11,None, 40,60, 40,60, 0,    400,600, 10,25, 2.7,None, 2,None,  25,None, 0.2,None, 0.3,None, 2,None, 0.1,None, 0.4,None, 65,None,   200,None, 0.27,40, 2,None, 90,None, 30,None, 100,None, 400,None, 120,None, 6,40,   'infant'),
        # Children 1-3
        (1, 3, 'both', 'normal', 1000,1400,  13,None, 30,40, 50,60, 14,   300,600, 15,50, 6,200,   30,None, 15,400, 0.5,None, 0.5,None, 6,None, 0.5,30,  0.9,None, 150,300,   700,2500, 7,40,  3,7,  90,200, 65,65,  460,None, 2000,None, 1000,None, 17,90,  'schofield_child'),
        # Children 4-6
        (4, 6, 'both', 'normal', 1200,1600,  15,None, 25,35, 50,60, 17,   400,900, 15,50, 7,200,   55,None, 25,650, 0.6,None, 0.6,None, 8,None, 0.6,30,  1.2,None, 200,400,   1000,2500, 10,40, 4,8,  90,200, 76,76,  500,None, 2300,None, 1400,None, 22,150, 'schofield_child'),
        # Children 7-9
        (7, 9, 'both', 'normal', 1500,1900,  19,None, 25,35, 50,60, 20,   450,900, 15,50, 8,200,   55,None, 35,650, 0.9,None, 0.9,None, 9,None, 0.9,30,  1.5,None, 250,600,   1100,2500, 10,40, 5,9,  90,200, 100,None,700,None, 2700,None, 1900,None, 25,150, 'schofield_child'),
        # Boys 10-18
        (10,18, 'male', 'normal', 2000,3000, 34,None, 25,35, 50,60, 26,   600,1700, 15,50, 10,300, 75,None, 40,1800, 1.0,None, 1.3,None, 12,None, 1.2,60, 2.4,None, 330,900,  1200,3000, 14,45, 9,14, 120,900, 200,None,1250,None, 3500,None, 2200,None, 37,150, 'schofield_male'),
        # Girls 10-18
        (10,18,'female','normal', 1800,2500, 34,None, 25,35, 50,60, 26,   600,1700, 15,50, 10,300, 75,None, 40,1800, 1.0,None, 1.0,None, 11,None, 1.0,60, 2.4,None, 330,900,  1200,3000, 20,45, 7,14, 120,900, 200,None,1250,None, 3500,None, 2200,None, 37,150, 'schofield_female'),
        # Men 19-59
        (19,59,'male', 'normal', 2200,3000,  56,None, 20,35, 45,65, 30,   625,3000, 15,50, 10,300, 120,None,40,2000, 1.2,None, 1.3,None, 16,None, 1.3,100, 2.4,None,400,1000,  1000,2500, 8,45,  11,40, 150,600, 350,None,700,None, 3500,None, 2300,None, 55,400, 'schofield_male'),
        # Women 19-59
        (19,59,'female','normal', 1800,2400, 46,None, 20,35, 45,65, 25,   500,3000, 15,50, 10,300, 90,None, 40,1000, 1.1,None, 1.1,None, 14,None, 1.3,80,  2.4,None,400,1000,  1000,2500, 18,45, 8,40,  150,600, 265,None,700,None, 3500,None, 2300,None, 55,400, 'schofield_female'),
        # Elderly Men 60+
        (60,120,'male','normal', 2000,2500,  56,None, 20,35, 45,65, 30,   625,3000, 20,50, 10,300, 120,None,45,2000, 1.2,None, 1.3,None, 16,None, 1.7,100, 2.4,None,400,1000,  1200,2500, 8,45,  11,40, 150,600, 350,None,700,None, 3500,None, 2300,None, 55,400, 'schofield_male'),
        # Elderly Women 60+
        (60,120,'female','normal',1600,2000, 46,None, 20,35, 45,65, 21,   500,3000, 20,50, 10,300, 90,None, 45,1000, 1.1,None, 1.1,None, 14,None, 1.5,80,  2.4,None,400,1000,  1200,2500, 8,45,  8,40,  150,600, 265,None,700,None, 3500,None, 2300,None, 55,400, 'schofield_female'),
    ]

    cols = """age_min,age_max,gender,life_stage,
              energy_kcal_min,energy_kcal_max,
              protein_g_min,protein_g_max,fat_pct_min,fat_pct_max,carb_pct_min,carb_pct_max,fiber_g_min,
              vit_a_ug_min,vit_a_ug_max,vit_d_ug_min,vit_d_ug_max,vit_e_mg_min,vit_e_mg_max,vit_k_ug_min,vit_k_ug_max,
              vit_c_mg_min,vit_c_mg_max,vit_b1_mg_min,vit_b1_mg_max,vit_b2_mg_min,vit_b2_mg_max,vit_b3_mg_min,vit_b3_mg_max,
              vit_b6_mg_min,vit_b6_mg_max,vit_b12_ug_min,vit_b12_ug_max,folate_ug_min,folate_ug_max,
              calcium_mg_min,calcium_mg_max,iron_mg_min,iron_mg_max,zinc_mg_min,zinc_mg_max,
              iodine_ug_min,iodine_ug_max,magnesium_mg_min,magnesium_mg_max,phosphorus_mg_min,phosphorus_mg_max,
              potassium_mg_min,potassium_mg_max,sodium_mg_min,sodium_mg_max,selenium_ug_min,selenium_ug_max,
              bmr_formula"""

    placeholders = ",".join(["?"] * 54)
    c.executemany(
        f"INSERT OR IGNORE INTO nutritional_requirements({cols}) VALUES({placeholders})",
        req_data
    )

    # --- Special Requirements (WHO/FAO) ---
    special = [
        ('pregnant_t1', 'حامل - الثلث الأول',    85,  1,  0,   0,  0, 10, 0,   0,   0.1,  0.2, 200,   0,   9, 0, 25,  0,  4),
        ('pregnant_t2', 'حامل - الثلث الثاني',  285,  10, 0,  70,  0, 10, 0,   0,   0.1,  0.2, 200,  0,  9,  0, 25,  25, 4),
        ('pregnant_t3', 'حامل - الثلث الثالث',  475,  31, 0, 70,   0, 10, 0,   0,   0.1,  0.2, 200,  0,  9,  0, 25,  25, 4),
        ('lactating',   'مرضعة',                 500,  19, 0, 350,  0, 25, 0.2, 0,   0.3,  0.3,  60,  0,  4,  0,  50, 75, 15),
        ('infant_0_6',  'رضيع 0-6 أشهر',           0,  0,  0,   0,  0,  0, 0,   0,   0,    0,    0,   0,  0,  0,  0,   0,  0),
        ('infant_7_12', 'رضيع 7-12 شهراً',          0,  0,  0,   0,  0,  0, 0,   0,   0,    0,    0,   0,  0,  0,  0,   0,  0),
    ]
    cols2 = """life_stage,label_ar,extra_energy_kcal,extra_protein_g,extra_fat_g,
               extra_vit_a_ug,extra_vit_d_ug,extra_vit_c_mg,extra_vit_b1_mg,extra_vit_b2_mg,
               extra_vit_b6_mg,extra_vit_b12_ug,extra_folate_ug,extra_calcium_mg,extra_iron_mg,
               extra_zinc_mg,extra_iodine_ug,extra_magnesium_mg,extra_selenium_ug"""
    c.executemany(
        f"INSERT OR IGNORE INTO special_requirements({cols2}) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        special
    )

    # --- Food Composition from JORDAN_FOODS (per 100g) ---
    try:
        from jordan_food_composition import JORDAN_FOODS
    except ImportError:
        import importlib.util, os
        spec = importlib.util.spec_from_file_location(
            "jordan_food_composition",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "jordan_food_composition.py")
        )
        mod = importlib.util.load_from_spec(spec); spec.loader.exec_module(mod)
        JORDAN_FOODS = mod.JORDAN_FOODS

    c.executemany("""
        INSERT OR IGNORE INTO food_composition
        (food_code,food_name_ar,food_name_en,food_group_id,energy_kcal,protein_g,fat_g,carb_g,fiber_g,
         vit_a_ug,vit_d_ug,vit_e_mg,vit_k_ug,vit_c_mg,vit_b1_mg,vit_b2_mg,vit_b3_mg,vit_b6_mg,vit_b12_ug,folate_ug,
         calcium_mg,iron_mg,zinc_mg,iodine_ug,magnesium_mg,phosphorus_mg,potassium_mg,sodium_mg,selenium_ug)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, JORDAN_FOODS)


if __name__ == "__main__":
    init_database()

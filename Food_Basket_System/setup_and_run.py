#!/usr/bin/env python3
"""
setup_and_run.py  —  تثبيت المتطلبات وتشغيل نظام السلة الغذائية الأردنية
"""
import subprocess, sys, os

PACKAGES = [
    "flask>=2.3",
    "pandas>=1.5",
    "numpy>=1.23",
    "scipy>=1.9",
    "openpyxl>=3.0",
    "werkzeug>=2.3",
]

def install():
    print("📦 تثبيت المكتبات المطلوبة...")
    for pkg in PACKAGES:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "-q"],
            capture_output=True
        )
        if result.returncode != 0:
            # Try with --break-system-packages (Linux distro Python)
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "-q", "--break-system-packages"],
                capture_output=True
            )
        print(f"  ✔ {pkg}")
    print()

def check_imports():
    missing = []
    for mod in ['flask','pandas','numpy','scipy','openpyxl']:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing

def main():
    print("=" * 55)
    print("🌿  نظام السلة الغذائية الأردنية")
    print("    Jordan Food Basket System — FAO/WHO Methodology")
    print("=" * 55)

    missing = check_imports()
    if missing:
        print(f"⚠️  مكتبات مفقودة: {missing}")
        install()
        missing = check_imports()
        if missing:
            print(f"❌ فشل التثبيت: {missing}")
            print("   شغّل يدوياً: pip install flask pandas scipy openpyxl")
            sys.exit(1)
    else:
        print("✅ جميع المكتبات موجودة\n")

    # Init DB
    print("🗄️  تهيئة قاعدة البيانات...")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from database.init_db import init_database
    init_database()

    print("\n" + "=" * 55)
    print("🌐  افتح المتصفح على: http://127.0.0.1:5000")
    print("    اضغط Ctrl+C لإيقاف الخادم")
    print("=" * 55 + "\n")

    from app import app
    app.run(debug=False, host="127.0.0.1", port=5000)

if __name__ == "__main__":
    main()

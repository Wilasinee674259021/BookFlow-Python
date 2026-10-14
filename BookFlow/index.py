import sys
import os

# เพิ่มโฟลเดอร์ปัจจุบัน (BookFlow) เข้าไปใน sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app

if __name__ == "__main__":
    app.run()

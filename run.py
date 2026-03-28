import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from database import init_db
from app import app

if __name__ == "__main__":
    init_db()
    print("STS Seed Recorder running at http://localhost:5000")
    app.run(debug=True, port=5000)

# repair_alembic.py
from alembic.config import Config
from alembic import command

def repair():
    print("🔧 Attempting to repair Alembic version history...")
    alembic_cfg = Config("alembic.ini")
    
    # This command forces the database to mark itself as "up to date" 
    # with the latest code, ignoring the missing 'a5e7...' file.
    command.stamp(alembic_cfg, "head")
    print("✅ Success! Database version stamped to current HEAD.")

if __name__ == "__main__":
    repair()

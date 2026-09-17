"""
Manage retailers, stores and kiosks from the command line.

    python manage_tenancy.py list
    python manage_tenancy.py add-retailer <CODE> "<Name>"
    python manage_tenancy.py add-store <RETAILER_CODE> <STORE_CODE> "<Name>"
    python manage_tenancy.py add-kiosk <RETAILER_CODE> <STORE_CODE> <KIOSK_CODE>

<KIOSK_CODE> must match KIOSK_ID in that kiosk's .env. (Phase 2 replaces this
with secure kiosk enrollment.)
"""
import sys

from app import create_app, db
from app.models import Kiosk, Retailer, Store
from app.tenancy import repository, setup


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    command, args = argv[0], argv[1:]
    app = create_app()
    with app.app_context():
        if command == "list":
            for retailer in Retailer.query.order_by(Retailer.code):
                print(f"{retailer.code}  {retailer.name}")
                for store in Store.query.filter_by(retailer_id=retailer.retailer_id).order_by(Store.code):
                    print(f"  {store.code}  {store.name}")
                    for kiosk in Kiosk.query.filter_by(store_id=store.store_id).order_by(Kiosk.code):
                        state = "" if kiosk.is_active else "  (inactive)"
                        print(f"    kiosk {kiosk.code}{state}")
            return 0
        if command == "add-retailer" and len(args) == 2:
            setup.create_retailer(args[0], args[1])
        elif command == "add-store" and len(args) == 3:
            retailer = repository.get_retailer_by_code(args[0])
            if not retailer:
                print(f"Retailer {args[0]} not found")
                return 1
            setup.create_store(retailer, args[1], args[2])
        elif command == "add-kiosk" and len(args) == 3:
            retailer = repository.get_retailer_by_code(args[0])
            store = repository.get_store_by_code(retailer.retailer_id, args[1]) if retailer else None
            if not store:
                print(f"Store {args[0]}/{args[1]} not found")
                return 1
            setup.create_kiosk(store, args[2])
        else:
            print(__doc__)
            return 1
        db.session.commit()
        print("Done.")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

r"""
Manage retailers, stores and kiosks from the command line.

    python manage_tenancy.py list
    python manage_tenancy.py add-retailer <CODE> "<Name>"
    python manage_tenancy.py add-store <RETAILER_CODE> <STORE_CODE> "<Name>"
    python manage_tenancy.py add-kiosk <RETAILER_CODE> <STORE_CODE> <KIOSK_CODE>
    python manage_tenancy.py issue-dev-key <KIOSK_CODE> [--write-env <path to kiosk_agent\.env>]
    python manage_tenancy.py issue-staging-key <KIOSK_CODE> --secret-name <Secrets Manager secret> [--days N]
    python manage_tenancy.py revoke-keys <KIOSK_CODE>

issue-dev-key creates a DEVELOPMENT key for the kiosk agent (shown once, or
written to the agent's .env as KIOSK_DEV_KEY). Development keys only work
while the Core API listens on 127.0.0.1 and expire after DEV_KEY_MAX_DAYS.

issue-staging-key creates a cloud dev/staging key (DEVICE_AUTH_MODE=staging-key)
and writes it straight into the given Secrets Manager secret; the value is
never printed. It expires after STAGING_KEY_MAX_DAYS (default 14) unless
--days gives a shorter lifetime. Production kiosk enrollment replaces both
key types in a later phase.
"""
import sys

from app import create_app, db
from app.models import Kiosk, Retailer, Store
from app.tenancy import device_auth, repository, setup
from cloud_secrets import store_secret


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
        elif command == "issue-dev-key" and args:
            kiosk = repository.get_kiosk_by_code(args[0])
            if not kiosk:
                print(f"Kiosk {args[0]} not found")
                return 1
            key = device_auth.issue_development_key(kiosk)
            db.session.commit()
            if "--write-env" in args and args.index("--write-env") + 1 < len(args):
                write_env(args[args.index("--write-env") + 1], {
                    "KIOSK_ID": kiosk.code, "KIOSK_DEV_KEY": key})
                print(f"Development key for {kiosk.code} written to the agent .env")
            else:
                print(f"Development key for {kiosk.code} (shown once, keep it private):")
                print(key)
            return 0
        elif command == "issue-staging-key" and args:
            kiosk = repository.get_kiosk_by_code(args[0])
            if not kiosk:
                print(f"Kiosk {args[0]} not found")
                return 1
            if "--secret-name" not in args or args.index("--secret-name") + 1 >= len(args):
                print("issue-staging-key requires --secret-name <Secrets Manager secret name>")
                return 1
            secret_name = args[args.index("--secret-name") + 1]
            days = None
            if "--days" in args and args.index("--days") + 1 < len(args):
                days = int(args[args.index("--days") + 1])
            key = device_auth.issue_staging_key(kiosk, days=days)
            db.session.commit()
            store_secret(secret_name, key)
            print(f"Staging key for {kiosk.code} stored in Secrets Manager secret "
                 f"{secret_name!r} (value not printed).")
            return 0
        elif command == "revoke-keys" and args:
            kiosk = repository.get_kiosk_by_code(args[0])
            if not kiosk:
                print(f"Kiosk {args[0]} not found")
                return 1
            count = device_auth.revoke_kiosk_credentials(kiosk)
            db.session.commit()
            print(f"Revoked {count} key(s) for {kiosk.code}")
            return 0
        else:
            print(__doc__)
            return 1
        db.session.commit()
        print("Done.")
        return 0


def write_env(path, values):
    """Set KEY=value lines in an .env file, keeping every other line."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except FileNotFoundError:
        lines = []
    remaining = dict(values)
    out = []
    for line in lines:
        name = line.split("=", 1)[0].strip()
        if name in remaining:
            out.append(f"{name}={remaining.pop(name)}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in remaining.items())
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

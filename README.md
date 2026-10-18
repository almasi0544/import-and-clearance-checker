# Import Clearance Document Checker

Finds mismatches between the commercial invoice, packing list and bill of lading before they are
submitted for customs clearance. A person reviews every finding. It never submits anything to customs
and does not guarantee approval.

AMD Developer Hackathon ACT III, Reinvent Commerce track.

## How it works
The AI extracts, the code verifies, a person decides.

1. Evolus document extractors read each PDF and return JSON.
2. A normalizer turns that JSON into one fixed shape (schema v1). It fixes the shape only and never invents a value.
3. The checks engine compares the three documents with plain rules, no AI. A field that is missing on one document is never treated as a mismatch.
4. Each finding shows the values from every document, so a person can decide.

Checks implemented: C1 consignee name, C2 shipper name, C3 gross weight, C4 package count and type,
C5 quantity, C6 invoice arithmetic.

## Try the demo (no API key needed)
The ten synthetic test sets come with their saved extractions. Python 3.12 or newer:

    pip install -r backend/requirements.txt
    python backend/scripts/check_set.py 1
    python backend/scripts/check_set.py 6

Set 1 is clean and passes all six checks. Set 6 contains one planted quantity mismatch and gives one finding.
Any set from 1 to 10 works. Each result is compared with the answer key in test-data/. With your own Evolus
key in .env, add --live to extract again from the PDFs.

## Run the API with Docker
    docker build -t clearance-checker .
    docker run -d --name cc -p 8000:8000 -e SECRET_KEY=<random, 32+ characters> -e DEMO_MODE=true -e DEMO_PASSWORD=<12+ characters, demo only> clearance-checker
    docker exec cc python -c "import os; from app.db.database import Database; from app.db.migrate import migrate; db = Database.connect(os.environ['DATABASE_URL']); migrate(db); db.close()"
    docker exec cc python scripts/seed_demo_users.py
    docker exec cc python scripts/set_demo_passwords.py

Open http://127.0.0.1:8000/docs and log in at POST /auth/login with importer@demo.test, agent@demo.test,
reviewer@demo.test or admin@demo.test and the DEMO_PASSWORD you chose. These are demo accounts only.
The database lives inside the container and is lost when the container is removed.

## Environment variables
Copy .env.example to .env. The main ones:

- SECRET_KEY: signs login tokens. At least 32 random characters. Never commit it.
- DATABASE_URL: sqlite:///path or postgresql://...
- TOKEN_EXPIRE_MINUTES: token lifetime, 60 by default, 1440 at most.
- UPLOAD_DIR and MAX_UPLOAD_MB: where uploads go and the size limit.
- DEMO_MODE and DEMO_PASSWORD: only for the demo accounts. At least 12 characters.
- EVOLUS_API_KEY, EVOLUS_APPLICATION_ID, EVOLUS_AGENT_ID: Evolus access.
- EVOLUS_EXTRACTOR_INVOICE_ID, EVOLUS_EXTRACTOR_PACKING_LIST_ID, EVOLUS_EXTRACTOR_BILL_OF_LADING_ID:
  each written as extractorId:outputStructureId, both copied from the extractor API tab in Evolus.

## Run the tests
    pip install -r backend/requirements.txt pytest httpx
    python -m pytest tests -q

The tests use temporary databases and a fake Evolus client, so they need no key.

## Security: what is implemented and tested
- Passwords are hashed with Argon2. A wrong password and an unknown email give the same error.
- Login tokens are signed and expire. The role is read from the database on every request.
- Another user's shipment returns 404, the same as a missing one, on show, upload and list. This is tested over real HTTP.
- Uploads are checked by file content, not by file name, and the size is limited.
- Logins, shipment creation and uploads write audit events.
- Secrets live only in the environment. .env is never committed, and the Docker image runs as a non-root user and contains no secrets.

## Honest limits
- Evolus extraction is not perfect. On the ten synthetic sets, six match the answer key exactly (1, 2, 3, 6, 9, 10).
  On sets 4, 5 and 7 the extractor misread the bill of lading or the packing list, which produced extra findings.
  Those are false alarms that a person reviews. On set 8 one planted error (C6) was not flagged.
  On set 2 the extractor returned a subtotal that is not printed on the invoice.
- Only checks C1 to C6 are implemented.
- The demo runs from the command line. There is no route yet that takes an upload through extraction and checks in one request.
- All test documents are invented. Nothing was tested on real shipments or personal data.

## Team
Almasi: security, login and access control, Evolus extraction, Docker.
Jackma: application, data model, API, checks engine.

License: MIT

# ---------------------------------------------------------------------------
# PATCH fuer run.py — Stage 60 integrieren
# ---------------------------------------------------------------------------
# 1. In der STAGES-Liste am Ende anfuegen:
#
#    from pipeline import stage_60_cloud_export as s60
#
#    STAGES = [
#        ...
#        # Stage 60 — Cloud-Export (pro Sprache)
#        {
#            "id": "60",
#            "name": "cloud_export",
#            "module": s60,
#            "per_lang": True,   # wird fuer jede Zielsprache einzeln aufgerufen
#        },
#    ]
#
# 2. Im Stage-Dispatcher (wo run_stage aufgerufen wird) muss "per_lang" berueck-
#    sichtigt werden. Falls run.py bereits ueber TARGET_LANGUAGES iteriert,
#    einfach s60.run(book_slug, lang) aufrufen.
#
# Minimaler Aufruf-Block (falls run.py noch kein per_lang kennt):
#
#    if "60" in requested_stages:
#        for lang in config.TARGET_LANGUAGES:
#            s60.run(book_slug, lang, force=args.force, dry=args.dry)
#
# ---------------------------------------------------------------------------
# PATCH fuer config.py — GCS_BUCKET hinzufuegen
# ---------------------------------------------------------------------------
# In config.py (nach den bestehenden Konstanten) einfuegen:
#
#    # Cloud-Export (Stage 60)
#    GCS_BUCKET = os.getenv("GCS_BUCKET", "readlayer-taella-content")
#
# Und in .env:
#    GCS_BUCKET=readlayer-taella-content   # <-- echter Bucket-Name einsetzen
#
# ---------------------------------------------------------------------------
# NEUER GCS-BUCKET anlegen (einmalig, PowerShell / gcloud CLI):
# ---------------------------------------------------------------------------
#
#   gcloud storage buckets create gs://readlayer-taella-content \
#       --location=europe-west3 \
#       --uniform-bucket-level-access \
#       --project=readlayercloud
#
#   # Service Account hat bereits Storage-Rechte? Falls nicht:
#   gcloud projects add-iam-policy-binding readlayercloud \
#       --member="serviceAccount:service@readlayercloud.iam.gserviceaccount.com" \
#       --role="roles/storage.objectAdmin"
#
# ---------------------------------------------------------------------------

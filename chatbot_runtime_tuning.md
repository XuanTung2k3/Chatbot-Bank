## Runtime Tuning Commands (Cloud Run)

Use these commands to reduce cold starts and improve multi-user response stability.

```bash
gcloud run services update m-finance \
  --region=us-central1 \
  --min-instances=1 \
  --concurrency=40 \
  --cpu=1 \
  --memory=512Mi

gcloud run services update non-m-finance \
  --region=us-central1 \
  --min-instances=1 \
  --concurrency=40 \
  --cpu=1 \
  --memory=512Mi

gcloud run services update emp-spa \
  --region=us-central1 \
  --min-instances=1 \
  --concurrency=40 \
  --cpu=1 \
  --memory=512Mi

gcloud run services update non-emp-spa \
  --region=us-central1 \
  --min-instances=1 \
  --concurrency=40 \
  --cpu=1 \
  --memory=512Mi
```

Optional: increase `--min-instances` to `2` for peak periods.

from django.conf import settings
from django.db import models

class ProcessingJob(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="papyronix_jobs")
    operation = models.CharField(max_length=40)
    input_names = models.JSONField(default=list, blank=True)
    output_name = models.CharField(max_length=255, blank=True)
    input_bytes = models.PositiveBigIntegerField(default=0)
    succeeded = models.BooleanField(default=False)
    error_code = models.CharField(max_length=40, blank=True)
    elapsed_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.operation} · {self.created_at:%Y-%m-%d %H:%M}"

class DocumentAsset(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="papyronix_documents")
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to="private_documents/%Y/%m/")
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    extracted_text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

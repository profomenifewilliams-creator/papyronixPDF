import hashlib
from django.conf import settings
from django.db import models

class InvestigationCase(models.Model):
    PRIORITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]
    STATUS_CHOICES = [("open", "Open"), ("review", "Under review"), ("pending", "Pending"), ("closed", "Closed")]
    case_number = models.CharField(max_length=40, unique=True)
    title = models.CharField(max_length=180)
    summary = models.TextField()
    priority = models.CharField(max_length=12, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="open")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="police_cases")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.case_number} — {self.title}"

class EvidenceItem(models.Model):
    case = models.ForeignKey(InvestigationCase, on_delete=models.PROTECT, related_name="evidence")
    file = models.FileField(upload_to="evidence/%Y/%m/")
    original_name = models.CharField(max_length=255)
    sha256 = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    collected_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    collected_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.file:
            digest = hashlib.sha256()
            for chunk in self.file.chunks():
                digest.update(chunk)
            self.sha256 = digest.hexdigest()
            super().save(update_fields=["sha256"])

class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    action = models.CharField(max_length=100)
    case = models.ForeignKey(InvestigationCase, null=True, blank=True, on_delete=models.PROTECT)
    detail = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

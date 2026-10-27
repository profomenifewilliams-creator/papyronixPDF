from django.contrib import admin
from .models import AuditEvent, EvidenceItem, InvestigationCase

@admin.register(InvestigationCase)
class CaseAdmin(admin.ModelAdmin):
    list_display = ("case_number", "title", "priority", "status", "created_by", "created_at")
    search_fields = ("case_number", "title")
    list_filter = ("priority", "status")

@admin.register(EvidenceItem)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ("case", "original_name", "sha256", "collected_by", "collected_at")
    readonly_fields = ("sha256", "collected_at")

@admin.register(AuditEvent)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("actor", "action", "case", "created_at")
    readonly_fields = ("actor", "action", "case", "detail", "created_at")

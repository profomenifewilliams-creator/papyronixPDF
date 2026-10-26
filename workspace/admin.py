from django.contrib import admin
from .models import DocumentAsset, ProcessingJob

@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("operation", "user", "succeeded", "input_bytes", "elapsed_ms", "created_at")
    list_filter = ("operation", "succeeded", "created_at")
    search_fields = ("operation", "output_name", "user__username")
    readonly_fields = tuple(field.name for field in ProcessingJob._meta.fields)

@admin.register(DocumentAsset)
class DocumentAssetAdmin(admin.ModelAdmin):
    list_display = ("original_name", "user", "size_bytes", "created_at")
    search_fields = ("original_name", "user__username")
    readonly_fields = ("original_name", "content_type", "size_bytes", "extracted_text", "created_at")

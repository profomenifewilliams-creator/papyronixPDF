import os
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import AuditEvent
from .tools_engine import fingerprint_stream, summarize_audit_jsonl

@login_required
def toolbench(request):
    context = {"hash_result": None, "audit_result": None, "tool_error": ""}
    if request.method == "POST":
        mode = request.POST.get("mode", "")
        uploaded = request.FILES.get("analysis_file")
        if not uploaded:
            context["tool_error"] = "Select a file to analyze."
        elif mode == "hash":
            if uploaded.size > 20 * 1024 * 1024:
                context["tool_error"] = "For this demo, hash files must be 20 MB or smaller."
            else:
                context["hash_result"] = {"filename": os.path.basename(uploaded.name)[:255], **fingerprint_stream(uploaded.file)}
                AuditEvent.objects.create(actor=request.user, action="tool.file_fingerprinted", detail=f"size_bytes={context['hash_result']['size_bytes']}")
        elif mode == "audit":
            if uploaded.size > 2 * 1024 * 1024:
                context["tool_error"] = "Audit logs must be 2 MB or smaller in this demo."
            else:
                try:
                    text = uploaded.read().decode("utf-8")
                    context["audit_result"] = summarize_audit_jsonl(text.splitlines())
                    AuditEvent.objects.create(actor=request.user, action="tool.audit_summary_created", detail=f"records_with_action={context['audit_result']['records_with_action']}")
                except UnicodeDecodeError:
                    context["tool_error"] = "The audit file must be UTF-8 JSON Lines, one JSON object per line."
                except ValueError as exc:
                    context["tool_error"] = str(exc)
        else:
            context["tool_error"] = "Unknown tool action."
    return render(request, "tools.html", context)

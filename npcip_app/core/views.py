import csv
import hashlib
from pathlib import Path
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import get_valid_filename
from .forms import CaseForm, EvidenceForm
from .models import AuditEvent, EvidenceItem, InvestigationCase

def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            return redirect("dashboard")
    else:
        form = UserCreationForm()
    return render(request, "register.html", {"form": form})


def _visible_cases(request):
    cases = InvestigationCase.objects.all()
    if not (request.user.is_staff or request.user.is_superuser):
        cases = cases.filter(created_by=request.user)
    return cases


def _audit(user, action, case=None, detail=""):
    AuditEvent.objects.create(actor=user, action=action, case=case, detail=detail[:400])

@login_required
def dashboard(request):
    cases = _visible_cases(request)
    audit = AuditEvent.objects.select_related("actor", "case")
    if not (request.user.is_staff or request.user.is_superuser):
        audit = audit.filter(actor=request.user)
    context = {
        "total_cases": cases.count(),
        "open_cases": cases.filter(status="open").count(),
        "critical_cases": cases.filter(priority="critical").exclude(status="closed").count(),
        "evidence_count": EvidenceItem.objects.count(),
        "recent_cases": cases[:6],
        "recent_audit": audit[:6],
    }
    return render(request, "dashboard.html", context)

@login_required
def case_list(request):
    query = request.GET.get("q", "").strip()
    cases = _visible_cases(request).select_related("created_by")
    if query:
        cases = cases.filter(case_number__icontains=query) | cases.filter(title__icontains=query)
    return render(request, "cases.html", {"cases": cases, "query": query})

@login_required
def case_create(request):
    if request.method == "POST":
        form = CaseForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.created_by = request.user
            obj.save()
            _audit(request.user, "case.created", obj, f"Created case {obj.case_number}")
            messages.success(request, "Investigation case created.")
            return redirect("case_detail", case_id=obj.pk)
    else:
        form = CaseForm()
    return render(request, "case_form.html", {"form": form})

@login_required
def case_detail(request, case_id):
    case = get_object_or_404(_visible_cases(request).select_related("created_by"), pk=case_id)
    evidence = case.evidence.select_related("collected_by")
    return render(request, "case_detail.html", {"case": case, "evidence": evidence})

@login_required
def evidence_upload(request, case_id):
    case = get_object_or_404(_visible_cases(request), pk=case_id)
    if request.method == "POST":
        form = EvidenceForm(request.POST, request.FILES)
        uploaded = request.FILES.get("file")
        if uploaded and uploaded.size > 20 * 1024 * 1024:
            form.add_error("file", "Files must be 20 MB or smaller.")
        if form.is_valid() and uploaded and uploaded.size <= 20 * 1024 * 1024:
            item = form.save(commit=False)
            item.case = case
            item.collected_by = request.user
            item.original_name = get_valid_filename(Path(uploaded.name).name)[:255]
            item.save()
            _audit(request.user, "evidence.uploaded", case, f"SHA-256 recorded for {item.original_name}: {item.sha256}")
            messages.success(request, "Evidence stored and SHA-256 fingerprint recorded.")
            return redirect("case_detail", case_id=case.pk)
    else:
        form = EvidenceForm()
    return render(request, "case_form.html", {"form": form, "case": case, "evidence_mode": True})

@login_required
def evidence_download(request, evidence_id):
    evidence = EvidenceItem.objects.select_related("case")
    if not (request.user.is_staff or request.user.is_superuser):
        evidence = evidence.filter(case__created_by=request.user)
    item = get_object_or_404(evidence, pk=evidence_id)
    try:
        item.file.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("Evidence file is unavailable on this demo instance.")
    digest = hashlib.sha256()
    for chunk in item.file.chunks():
        digest.update(chunk)
    item.file.seek(0)
    if digest.hexdigest() != item.sha256:
        item.file.close()
        _audit(request.user, "evidence.integrity_failed", item.case, f"Stored hash mismatch for evidence ID {item.pk}")
        raise Http404("Integrity verification failed; download blocked.")
    _audit(request.user, "evidence.downloaded", item.case, f"Verified SHA-256 before download for evidence ID {item.pk}")
    return FileResponse(item.file, as_attachment=True, filename=item.original_name)

@login_required
def audit_list(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponse("Administrator access required.", status=403)
    return render(request, "audit.html", {"events": AuditEvent.objects.select_related("actor", "case")[:250]})

@login_required
def case_export(request):
    if not (request.user.is_staff or request.user.is_superuser):
        return HttpResponse("Administrator access required.", status=403)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="npcip-case-register.csv"'
    writer = csv.writer(response)
    writer.writerow(["Case number", "Title", "Priority", "Status", "Created by", "Created at"])
    for item in InvestigationCase.objects.select_related("created_by"):
        writer.writerow([item.case_number, item.title, item.priority, item.status, item.created_by.username, item.created_at.isoformat()])
    _audit(request.user, "case.exported", detail="Exported case register CSV")
    return response

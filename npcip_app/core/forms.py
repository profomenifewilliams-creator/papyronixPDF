from django import forms
from .models import EvidenceItem, InvestigationCase

class CaseForm(forms.ModelForm):
    class Meta:
        model = InvestigationCase
        fields = ["case_number", "title", "summary", "priority", "status"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 4})}

class EvidenceForm(forms.ModelForm):
    class Meta:
        model = EvidenceItem
        fields = ["file", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

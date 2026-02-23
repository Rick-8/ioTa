from django import forms
from django_ckeditor_5.widgets import CKEditor5Widget

from .models import NewsStory


class NewsStoryForm(forms.ModelForm):
    class Meta:
        model = NewsStory
        fields = ["title", "image", "synopsis", "body", "is_breaking", "is_archived"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "iota-input"}),
            "synopsis": forms.Textarea(attrs={"class": "iota-input", "rows": 4}),
            "body": CKEditor5Widget(
                attrs={"class": "iota-input django_ckeditor_5"},
                config_name="extends",
            ),
        }
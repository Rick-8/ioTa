from django import forms
from .models import Question, Choice
from .models import Course
from django.utils.text import slugify



class ChoiceForm(forms.ModelForm):
    class Meta:
        model = Choice
        fields = ['text', 'is_correct']
        widgets = {
            'text': forms.TextInput(attrs={'class': 'form-control'}),
        }


ChoiceFormSet = forms.inlineformset_factory(
    Question,
    Choice,
    form=ChoiceForm,
    extra=4,        # number of answer boxes that appear
    can_delete=True
)


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['module', 'text', 'order']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control'}),
            'module': forms.Select(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


# ======================
# COURSE CREATION FORM
# ======================

class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["title", "slug", "description", "order", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "slug": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "order": forms.NumberInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_slug(self):
        slug = self.cleaned_data["slug"]
        return slugify(slug)

from django.db import models
from django.db import transaction
from django.utils.text import slugify


class NewsStory(models.Model):
    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=260, unique=True, blank=True)

    synopsis = models.TextField(max_length=500, help_text="Short summary shown on the list page.")
    body = models.TextField(help_text="Full story content.")
    image = models.ImageField(upload_to="news/", blank=True, null=True)

    is_breaking = models.BooleanField(default=False, help_text="Only one story can be Breaking at a time.")
    is_archived = models.BooleanField(default=False, help_text="Archived stories are hidden from the main list.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Slug generation
        if not self.slug:
            base = slugify(self.title)[:240] or "story"
            candidate = base
            i = 2
            while NewsStory.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{i}"
                i += 1
            self.slug = candidate

        super().save(*args, **kwargs)

        # Enforce one breaking story (and don't allow archived to stay breaking)
        if self.is_archived and self.is_breaking:
            NewsStory.objects.filter(pk=self.pk).update(is_breaking=False)
            self.is_breaking = False

        if self.is_breaking:
            NewsStory.objects.exclude(pk=self.pk).filter(is_breaking=True).update(is_breaking=False)

    @classmethod
    def set_breaking(cls, story_id: int):
        with transaction.atomic():
            cls.objects.filter(is_breaking=True).update(is_breaking=False)
            cls.objects.filter(pk=story_id, is_archived=False).update(is_breaking=True)
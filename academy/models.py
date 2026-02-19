from django.conf import settings
from django.db import models
from django.utils import timezone


class Course(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=200)
    slug = models.SlugField()
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=1)
    min_score_to_pass = models.PositiveIntegerField(default=80)  # % required
    is_mandatory = models.BooleanField(default=True)

    class Meta:
        unique_together = ("course", "slug")
        ordering = ["order"]

    def __str__(self):
        return f"{self.course.title} – {self.title}"


class Lesson(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=1)
    content = models.TextField(help_text="HTML or markdown content for this lesson.")
    video_url = models.URLField(blank=True, help_text="Optional YouTube / Vimeo link")
    image_url = models.URLField(blank=True, help_text="Optional image link")   # NEW FIELD ✔

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.title



class Question(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="questions")
    text = models.TextField()
    order = models.PositiveIntegerField(default=1)
    explanation = models.TextField(
        blank=True,
        help_text="Shown after answering to reinforce learning."
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"Q{self.order} – {self.module.title}"


class Choice(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="choices")
    text = models.CharField(max_length=255)
    is_correct = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.question} – {self.text}"


class ModuleProgress(models.Model):
    STATUS_CHOICES = (
        ("not_started", "Not started"),
        ("in_progress", "In progress"),
        ("completed", "Completed"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_started")
    score = models.PositiveIntegerField(default=0)  # best score %
    completed_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "module")

    def __str__(self):
        return f"{self.user} – {self.module} – {self.status}"

    @property
    def passed(self):
        return self.score >= self.module.min_score_to_pass


class LessonProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("user", "lesson")

    def __str__(self):
        return f"{self.user} – {self.lesson} – {'Done' if self.completed else 'Pending'}"


class Certificate(models.Model):
    """
    Certificate issued when a user passes a specific module (e.g. final assessment).
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    module = models.ForeignKey(Module, on_delete=models.CASCADE)
    score = models.PositiveIntegerField()
    issued_at = models.DateTimeField(default=timezone.now)
    certificate_number = models.CharField(max_length=50, unique=True)

    class Meta:
        unique_together = ("user", "module")

    def __str__(self):
        return f"Certificate {self.certificate_number} – {self.user} – {self.course.title}"


class FinalTestSubmission(models.Model):
    """
    Stores a user's final test attempt for a module.
    Answers are stored as JSON so superusers can review later.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="final_test_submissions",
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="final_submissions",
    )
    submitted_at = models.DateTimeField(default=timezone.now)

    # List/dict of answers:
    # [
    #   {
    #       "question_id": 1,
    #       "question_text": "...",
    #       "selected_choice_id": 10,
    #       "selected_choice_text": "Safety, professionalism, customer service"
    #   },
    #   ...
    # ]
    answers = models.JSONField()

    reviewed = models.BooleanField(default=False)
    is_passed = models.BooleanField(default=False)
    feedback = models.TextField(blank=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_final_tests",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Final test – {self.user} – {self.module}"

    def save(self, *args, **kwargs):
        from .models import ModuleProgress  # avoid circular import at top

        # If this submission is being marked as passed, make sure ModuleProgress reflects that
        super().save(*args, **kwargs)

        if self.reviewed and self.is_passed:
            mp, _ = ModuleProgress.objects.get_or_create(
                user=self.user,
                module=self.module,
                defaults={"status": "completed"},
            )
            mp.status = "completed"
            mp.score = max(mp.score, 100)  # or any score you want for "passed"
            now = timezone.now()
            mp.completed_at = mp.completed_at or now
            mp.last_attempt_at = now
            mp.save()


class ManagerDocument(models.Model):
    file = models.FileField(upload_to="documents/")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name


class CourseAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="academy_assignments",
        null=True,
        blank=True
    )
    group = models.ForeignKey(
        "auth.Group",
        on_delete=models.CASCADE,
        related_name="academy_assignments",
        null=True,
        blank=True
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        owner = self.user or self.group
        return f"{owner} → {self.course}"

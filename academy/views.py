# academy/views.py

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from .models import ManagerDocument
from django.http import HttpResponse, HttpResponseForbidden
from .models import Certificate, ModuleProgress, FinalTestSubmission
from django.conf import settings
from reportlab.lib.utils import ImageReader
from .forms import QuestionForm, ChoiceFormSet
import json
from django.contrib.admin.views.decorators import staff_member_required
from .models import Question, Choice, Module
from django.db.models import Q
from .models import Course, CourseAssignment
import os


from .models import (
    Course,
    Module,
    Lesson,
    LessonProgress,
    ModuleProgress,
    Question,
    Choice,
    FinalTestSubmission,
    Certificate,
)


def _update_module_progress_from_lessons(user, module):
    """
    Recalculate ModuleProgress for a user/module based on lesson completion.

    For now:
      - score = percentage of lessons completed (0–100)
      - status:
          0%      -> not_started
          1–99%   -> in_progress
          100%    -> completed
    """
    module_progress = _get_module_progress(user, module)

    lessons = module.lessons.all()
    total = lessons.count()

    if total == 0:
        # No lessons: treat as completed module
        module_progress.score = 100
        module_progress.status = "completed"
        if module_progress.completed_at is None:
            module_progress.completed_at = timezone.now()
    else:
        completed_count = LessonProgress.objects.filter(
            user=user,
            lesson__module=module,
            completed=True,
        ).count()

        percent = int((completed_count / total) * 100)

        module_progress.score = percent

        if percent == 0:
            module_progress.status = "not_started"
            module_progress.completed_at = None
        elif percent < 100:
            module_progress.status = "in_progress"
            module_progress.completed_at = None
        else:
            module_progress.status = "completed"
            if module_progress.completed_at is None:
                module_progress.completed_at = timezone.now()

    module_progress.last_attempt_at = timezone.now()
    module_progress.save()
    return module_progress


def _can_access_module(user, module):
    """
    Returns True if the user has passed all previous mandatory modules in this course.
    'Passed' means ModuleProgress.score >= module.min_score_to_pass.
    """
    previous_modules = module.course.modules.filter(
        order__lt=module.order,
        is_mandatory=True,
    )

    for m in previous_modules:
        prog = ModuleProgress.objects.filter(user=user, module=m).first()
        if not prog or not prog.passed:
            return False
    return True


def _get_module_progress(user, module):
    """
    Convenience helper to get or create ModuleProgress.
    """
    progress, _ = ModuleProgress.objects.get_or_create(
        user=user,
        module=module,
        defaults={"status": "not_started"},
    )
    return progress


def _issue_certificate_if_needed(request, module_progress):
    """
    Create a Certificate for this user+module if one doesn't already exist,
    and email the admins a link to it.
    """
    user = module_progress.user
    module = module_progress.module
    course = module.course

    existing = Certificate.objects.filter(user=user, module=module).first()
    if existing:
        return existing

    # Generate a simple unique certificate number
    timestamp = int(timezone.now().timestamp())
    cert_number = f"COZY-{course.id}-{module.id}-{user.id}-{timestamp}"

    certificate = Certificate.objects.create(
        user=user,
        course=course,
        module=module,
        score=module_progress.score,
        certificate_number=cert_number,
    )

    # Build URL to the certificate detail page
    url = request.build_absolute_uri(
        reverse("academy_certificate_detail", args=[certificate.id])
    )

    # Email all admins (uses settings.ADMINS)
    subject = (
        f"New Driver Induction certificate – "
        f"{user.get_full_name() or user.username}"
    )
    message = (
        f"{user.get_full_name() or user.username} has passed "
        f"'{course.title}' – module '{module.title}' with a score of "
        f"{module_progress.score}%.\n\n"
        f"Certificate number: {certificate.certificate_number}\n"
        f"View/print the certificate here: {url}"
    )

    mail_admins(subject, message)

    return certificate


@login_required
def dashboard(request):
    """
    Show only assigned courses (user or group) and the user's progress in each.
    """

    # 1. Get course IDs assigned to this user OR their groups
    assigned_course_ids = CourseAssignment.objects.filter(
        Q(user=request.user) |
        Q(group__in=request.user.groups.all())
    ).values_list("course_id", flat=True)

    # 2. Load the assigned courses, still respecting is_active
    courses = Course.objects.filter(
        id__in=assigned_course_ids,
        is_active=True
    ).prefetch_related("modules").order_by("order")

    course_data = []

    # 3. Progress calculation remains EXACTLY the same
    for course in courses:
        modules = course.modules.all()
        total_modules = modules.count() or 1
        completed_modules = 0

        for module in modules:
            mp = ModuleProgress.objects.filter(
                user=request.user,
                module=module
            ).first()

            if mp and mp.passed:
                completed_modules += 1

        progress_percent = int((completed_modules / total_modules) * 100)

        course_data.append({
            "course": course,
            "progress_percent": progress_percent,
            "completed_modules": completed_modules,
            "total_modules": total_modules,
        })

    return render(request, "academy/dashboard.html", {
        "course_data": course_data,
    })


@login_required
def course_detail(request, course_slug):
    """
    Show all modules in a course, with lock/unlock and basic status.
    """
    course = get_object_or_404(Course, slug=course_slug, is_active=True)
    modules = course.modules.all()

    module_rows = []
    for module in modules:
        module_progress = ModuleProgress.objects.filter(
            user=request.user,
            module=module,
        ).first()
        can_access = _can_access_module(request.user, module)

        module_rows.append(
            {
                "module": module,
                "progress": module_progress,
                "can_access": can_access,
            }
        )

    context = {
        "course": course,
        "module_rows": module_rows,
    }
    return render(request, "academy/course_detail.html", context)


@login_required
def module_detail(request, course_slug, module_slug):
    """
    Show lessons in a module and lesson completion status.
    """
    course = get_object_or_404(Course, slug=course_slug, is_active=True)
    module = get_object_or_404(course.modules, slug=module_slug)

    # Check if user is allowed to access this module
    if not _can_access_module(request.user, module):
        messages.warning(request, "Please complete the previous modules first.")
        return redirect("academy_course_detail", course_slug=course.slug)

    # Get or create module progress record
    module_progress = _get_module_progress(request.user, module)

    lessons = module.lessons.all()

    lesson_rows = []
    for lesson in lessons:
        lp = LessonProgress.objects.filter(user=request.user, lesson=lesson).first()
        lesson_rows.append(
            {
                "lesson": lesson,
                "progress": lp,
            }
        )

    # Calculate % of lessons completed for display
    total_lessons = lessons.count() or 1
    completed_lessons = sum(
        1
        for row in lesson_rows
        if row["progress"] and row["progress"].completed
    )
    lesson_progress_percent = int((completed_lessons / total_lessons) * 100)

    # Update module_progress (score + status) based on lessons
    module_progress = _update_module_progress_from_lessons(request.user, module)

    context = {
        "course": course,
        "module": module,
        "lesson_rows": lesson_rows,
        "lesson_progress_percent": lesson_progress_percent,
        "module_progress": module_progress,
    }

    return render(request, "academy/module_detail.html", context)


@login_required
def module_quiz(request, course_slug, module_slug):
    """
    Multi-choice quiz for a module. Updates ModuleProgress.score and,
    if this is the final assessment module and the user passes,
    issues a certificate and emails admins.
    """
    course = get_object_or_404(Course, slug=course_slug, is_active=True)
    module = get_object_or_404(course.modules, slug=module_slug)

    # Respect module locking rules
    if not _can_access_module(request.user, module):
        messages.warning(request, "Please complete the previous modules first.")
        return redirect("academy_course_detail", course_slug=course.slug)

    questions = module.questions.prefetch_related("choices").all()
    if not questions.exists():
        messages.warning(request, "No questions have been set up for this module yet.")
        return redirect(
            "academy_module_detail",
            course_slug=course.slug,
            module_slug=module.slug,
        )

    module_progress = _get_module_progress(request.user, module)

    if request.method == "GET":
        context = {
            "course": course,
            "module": module,
            "questions": questions,
            "module_progress": module_progress,
            "score_percent": None,
            "passed": False,
            "answers_marked": [],
        }
        return render(request, "academy/module_quiz.html", context)

    # POST – mark answers
    total_questions = questions.count()
    correct_count = 0
    answers_marked = []

    for question in questions:
        field_name = f"question_{question.id}"
        choice_id = request.POST.get(field_name)
        selected_choice = None
        is_correct = False

        if choice_id:
            try:
                selected_choice = Choice.objects.get(id=choice_id, question=question)
                is_correct = selected_choice.is_correct
            except Choice.DoesNotExist:
                selected_choice = None

        if is_correct:
            correct_count += 1

        answers_marked.append(
            {
                "question": question,
                "selected_choice": selected_choice,
                "is_correct": is_correct,
            }
        )

    score_percent = int((correct_count / total_questions) * 100)

    # Update ModuleProgress (keep best score)
    if score_percent > module_progress.score:
        module_progress.score = score_percent

    module_progress.last_attempt_at = timezone.now()

    if module_progress.score >= module.min_score_to_pass:
        module_progress.status = "completed"
        if module_progress.completed_at is None:
            module_progress.completed_at = timezone.now()
        passed = True
    else:
        if module_progress.status == "not_started":
            module_progress.status = "in_progress"
        passed = False

    module_progress.save()

    # If this is the final assessment module and they passed, issue certificate
    # Adjust slug string to whatever you used in admin
    if passed and module.slug == "new-driver-induction-final-assessment":
        _issue_certificate_if_needed(request, module_progress)

    context = {
        "course": course,
        "module": module,
        "questions": questions,
        "module_progress": module_progress,
        "answers_marked": answers_marked,
        "score_percent": score_percent,
        "passed": passed,
    }
    return render(request, "academy/module_quiz.html", context)


@login_required
def academy_complete_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)

    # Get or create progress record
    progress, created = LessonProgress.objects.get_or_create(
        user=request.user,
        lesson=lesson,
    )

    # Mark as complete
    progress.completed = True
    if progress.completed_at is None:
        progress.completed_at = timezone.now()
    progress.save()

    # Update module progress now that this lesson is complete
    module = lesson.module
    _update_module_progress_from_lessons(request.user, module)

    # Always go back to the module page after completion
    return redirect(
        "academy_module_detail",
        course_slug=module.course.slug,
        module_slug=module.slug,
    )


@login_required
def lesson_detail(request, course_slug, module_slug, lesson_id):
    lesson = get_object_or_404(
        Lesson,
        id=lesson_id,
        module__slug=module_slug,
        module__course__slug=course_slug,
    )

    course = lesson.module.course
    module = lesson.module

    lesson_progress, _ = LessonProgress.objects.get_or_create(
        user=request.user,
        lesson=lesson,
    )

    context = {
        "course": course,
        "module": module,
        "lesson": lesson,
        "lesson_progress": lesson_progress,
    }
    return render(request, "academy/lesson_detail.html", context)


@login_required
def certificate_detail(request, certificate_id):
    certificate = get_object_or_404(Certificate, id=certificate_id)

    # Only allow admins/staff or the certificate owner to view
    if not (request.user.is_staff or request.user == certificate.user):
        return HttpResponseForbidden(
            "You do not have permission to view this certificate."
        )

    context = {
        "certificate": certificate,
    }
    return render(request, "academy/certificate_detail.html", context)


@login_required
def final_test(request, course_slug, module_slug):
    course = get_object_or_404(Course, slug=course_slug, is_active=True)
    module = get_object_or_404(course.modules, slug=module_slug)

    # Optional: only allow final test if previous mandatory modules are passed
    if not _can_access_module(request.user, module):
        messages.warning(request, "Please complete the previous modules first.")
        return redirect("academy_course_detail", course_slug=course.slug)

    questions = module.questions.prefetch_related("choices").all()

    if not questions:
        messages.error(request, "Final test questions have not been set up yet.")
        return redirect(
            "academy_module_detail",
            course_slug=course.slug,
            module_slug=module.slug,
        )

    if request.method == "POST":
        answers = []
        total_questions = questions.count()
        correct_count = 0

        for q in questions:
            field_name = f"question_{q.id}"
            selected_choice_id = request.POST.get(field_name)
            selected_choice = None
            selected_choice_text = None

            if selected_choice_id:
                selected_choice = q.choices.filter(id=selected_choice_id).first()
                if selected_choice:
                    selected_choice_text = selected_choice.text

            # Find the correct choice for this question
            correct_choice = q.choices.filter(is_correct=True).first()
            correct_choice_text = correct_choice.text if correct_choice else None

            # Mark correctness
            is_correct = (
                selected_choice is not None
                and correct_choice is not None
                and selected_choice.id == correct_choice.id
            )
            if is_correct:
                correct_count += 1

            answers.append(
                {
                    "question_id": q.id,
                    "question_text": q.text,
                    "selected_choice_id": selected_choice.id if selected_choice else None,
                    "selected_choice_text": selected_choice_text,
                    "correct_choice_text": correct_choice_text,
                    "is_correct": is_correct,
                    "explanation": q.explanation,
                }
            )

        # Save submission (now with marked answers + explanations)
        submission = FinalTestSubmission.objects.create(
            user=request.user,
            module=module,
            answers=answers,
        )

        # Calculate score as a percentage
        score_percent = int((correct_count / total_questions) * 100) if total_questions > 0 else 0

        # Email all superusers
        User = get_user_model()
        superuser_emails = list(
            User.objects.filter(is_superuser=True, is_active=True)
            .exclude(email__isnull=True)
            .exclude(email__exact="")
            .values_list("email", flat=True)
        )

        if superuser_emails:
            subject = (
                f"[Cozy Academy] Final test submitted: "
                f"{request.user} – {course.title} ({score_percent}%)"
            )

            body_lines = [
                f"User: {request.user} (ID: {request.user.id})",
                f"Course: {course.title}",
                f"Module: {module.title}",
                f"Submitted at: {submission.submitted_at}",
                f"Score: {correct_count} / {total_questions} ({score_percent}%)",
                "",
                "Answers:",
            ]

            for a in answers:
                body_lines.append("")
                body_lines.append(f"Q: {a['question_text']}")
                if a["selected_choice_text"]:
                    body_lines.append(f"Selected: {a['selected_choice_text']}")
                else:
                    body_lines.append("Selected: (no answer selected)")

                if a["correct_choice_text"]:
                    body_lines.append(f"Correct: {a['correct_choice_text']}")
                else:
                    body_lines.append("Correct: (no correct choice set)")

                body_lines.append(
                    f"Marked: {'CORRECT' if a['is_correct'] else 'INCORRECT'}"
                )

                if a["explanation"]:
                    body_lines.append(f"Explanation: {a['explanation']}")

            body = "\n".join(body_lines)

            send_mail(
                subject=subject,
                message=body,
                from_email=None,  # uses DEFAULT_FROM_EMAIL
                recipient_list=superuser_emails,
                fail_silently=True,
            )

        messages.success(
            request,
            "Your final test has been submitted and marked. "
            "A member of the operations team will review the results and update your status."
        )
        return redirect(
            "academy_module_detail",
            course_slug=course.slug,
            module_slug=module.slug,
        )

    # GET – show test form
    context = {
        "course": course,
        "module": module,
        "questions": questions,
    }
    return render(request, "academy/final_test.html", context)


def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_superuser)(view_func)


@superuser_required
def manager_dashboard(request):
    return render(request, "academy/manager/dashboard.html")


@superuser_required
def manager_final_tests(request):
    submissions = FinalTestSubmission.objects.all().order_by('-submitted_at')
    return render(request, "academy/manager/final_tests.html", {
        "submissions": submissions
    })


@superuser_required
def manager_driver_progress(request):
    progress = ModuleProgress.objects.select_related("user", "module").all()
    return render(request, "academy/manager/driver_progress.html", {
        "progress": progress
    })


@superuser_required
def manager_documents(request):
    return render(request, "academy/manager/documents.html")


@superuser_required
def manager_tools(request):
    return render(request, "academy/manager/tools.html")


@login_required
@user_passes_test(lambda u: u.is_superuser or Certificate.objects.filter(user=u).exists())
def generate_certificate_pdf(request, certificate_id):
    """
    Generate a stylish landscape certificate PDF with Cozy branding.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from django.templatetags.static import static

    certificate = get_object_or_404(Certificate, id=certificate_id)
    user = certificate.user
    course = certificate.course
    module = certificate.module

    # Only owner or superuser can access
    if not (request.user.is_superuser or request.user == user):
        return HttpResponseForbidden("You do not have permission to view this certificate.")

    # Landscape page setup
    page_width, page_height = landscape(A4)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="Cozy_Certificate_{certificate.id}.pdf"'

    # Initialize canvas
    p = canvas.Canvas(response, pagesize=landscape(A4))
    margin = 50

    # Colors
    burgundy = colors.HexColor("#800020")
    gray = colors.HexColor("#444444")

    # Background border
    p.setStrokeColor(burgundy)
    p.setLineWidth(4)
    p.rect(margin / 2, margin / 2, page_width - margin, page_height - margin, stroke=1, fill=0)

    # Logo (top-left)
    logo_path = os.path.join(settings.BASE_DIR, "static", "css", "media", "LOGO-Cozys.webp")
    logo = ImageReader(logo_path)
    p.drawImage(
        logo,
        x=margin,
        y=page_height - 130,
        width=180,
        height=80,
        mask="auto",
        preserveAspectRatio=True,
    )

        # Title
    p.setFont("Helvetica-Bold", 32)
    p.setFillColor(burgundy)
    p.drawCentredString(page_width / 2, page_height - 200, "Certificate of Completion")

    # Subtitle line
    p.setStrokeColor(gray)
    p.line(page_width / 4, page_height - 210, page_width * 3 / 4, page_height - 210)

    # Recipient
    p.setFillColor(gray)
    p.setFont("Helvetica", 16)
    p.drawCentredString(page_width / 2, page_height - 270, "This certifies that")

    p.setFont("Helvetica-Bold", 26)
    p.setFillColor(burgundy)
    name_text = user.get_full_name() or user.username
    p.drawCentredString(page_width / 2, page_height - 305, name_text)

    p.setFillColor(gray)
    p.setFont("Helvetica", 15)
    p.drawCentredString(page_width / 2, page_height - 335, "has successfully completed")

    # Course + module info
    p.setFont("Helvetica-Bold", 20)
    p.setFillColor(burgundy)
    p.drawCentredString(page_width / 2, page_height - 370, course.title)

    p.setFont("Helvetica", 13)
    p.setFillColor(gray)
    p.drawCentredString(page_width / 2, page_height - 395, f"Module: {module.title}")
    p.drawCentredString(page_width / 2, page_height - 415, f"Score Achieved: {certificate.score}%")

    # Issue details
    p.setFont("Helvetica-Oblique", 11)
    p.setFillColor(gray)
    p.drawCentredString(page_width / 2, margin + 80, f"Issued on {certificate.issued_at.strftime('%d %B %Y')}")
    p.drawCentredString(page_width / 2, margin + 60, f"Certificate No: {certificate.certificate_number}")

    # Footer
    p.setFont("Helvetica", 10)
    p.setFillColor(burgundy)
    p.drawCentredString(page_width / 2, margin + 35, "Cozy Coaches – Driver Academy")
    p.setFillColor(gray)
    p.drawCentredString(page_width / 2, margin + 20, "© Cozy Coaches Ltd. All rights reserved")

    # Save and return
    p.showPage()
    p.save()
    return response




@login_required
@user_passes_test(lambda u: u.is_superuser)
def manager_certificates(request):
    """View for superusers to manage and review certificates"""
    certificates = Certificate.objects.all().order_by("-issued_at")
    return render(request, "academy/manager/certificates.html", {
        "certificates": certificates,
    })


@superuser_required
def manager_documents(request):
    if request.method == "POST" and request.FILES.get("document"):
        ManagerDocument.objects.create(
            file=request.FILES["document"],
            uploaded_by=request.user,
        )
        messages.success(request, "Document uploaded successfully.")
        return redirect("academy_manager_documents")

    documents = ManagerDocument.objects.all().order_by("-uploaded_at")
    return render(request, "academy/manager/documents.html", {"documents": documents})


@superuser_required
def manager_final_tests(request):
    submissions = (
        FinalTestSubmission.objects
        .select_related("user", "module")
        .all()
        .order_by("-submitted_at")
    )

    # Attach summary stats to each submission instance
    for s in submissions:
        answers = s.answers or []
        total = len(answers)
        correct = sum(1 for a in answers if a.get("is_correct"))
        incorrect = total - correct

        if total > 0:
            score_percent = int((correct / total) * 100)
        else:
            score_percent = 0

        # Add attributes for the template to use
        s.total_questions = total
        s.correct_count = correct
        s.incorrect_count = incorrect
        s.score_percent = score_percent

    return render(
        request,
        "academy/manager/final_tests.html",
        {"submissions": submissions},
    )


@superuser_required
def manager_mark_pass(request, submission_id):
    """Mark a final test submission as passed, update progress, and generate certificate."""
    submission = get_object_or_404(FinalTestSubmission, id=submission_id)

    if request.method != "POST":
        return redirect("academy_manager_final_tests")

    submission.reviewed = True
    submission.is_passed = True
    submission.reviewed_by = request.user
    submission.reviewed_at = timezone.now()
    submission.save()

    # Update module progress
    mp, _ = ModuleProgress.objects.get_or_create(
        user=submission.user,
        module=submission.module,
        defaults={"status": "completed", "score": 100},
    )
    mp.status = "completed"
    mp.score = max(mp.score, 100)
    now = timezone.now()
    mp.completed_at = mp.completed_at or now
    mp.last_attempt_at = now
    mp.save()

    # 🟡 CREATE CERTIFICATE IF NONE EXISTS
    course = submission.module.course
    user = submission.user
    existing = Certificate.objects.filter(user=user, module=submission.module).first()

    if not existing:
        cert_number = f"COZY-{course.id}-{submission.module.id}-{user.id}-{int(now.timestamp())}"
        Certificate.objects.create(
            user=user,
            course=course,
            module=submission.module,
            score=mp.score,
            certificate_number=cert_number,
        )

        # Optional: notify admins
        messages.success(
            request,
            f"{user} has been marked as PASSED and a certificate has been generated."
        )
    else:
        messages.info(request, f"{user} already has a certificate for this module.")

    return redirect("academy_manager_final_tests")


from django.contrib.auth import get_user_model
User = get_user_model()


@superuser_required
def manager_users(request):
    """Full CRUD management for users by superusers, including username editing + course assignment."""
    from .models import Course, CourseAssignment

    User = get_user_model()
    users = User.objects.all().order_by("username")
    courses = Course.objects.all().order_by("title")

    if request.method == "POST":
        action = request.POST.get("action")
        user_id = request.POST.get("user_id")
        target_user = None

        if user_id:
            target_user = get_object_or_404(User, id=user_id)

        # Create new user
        if action == "create":
            username = request.POST.get("username")
            email = request.POST.get("email")
            password = request.POST.get("password")

            if not username or not password:
                messages.error(request, "Username and password are required.")
            elif User.objects.filter(username=username).exists():
                messages.warning(request, f"User '{username}' already exists.")
            else:
                User.objects.create_user(username=username, email=email, password=password)
                messages.success(request, f"User '{username}' created successfully.")

        # Update existing user
        elif action == "update" and target_user:
            new_username = request.POST.get("username") or target_user.username
            if new_username != target_user.username:
                if User.objects.filter(username=new_username).exclude(id=target_user.id).exists():
                    messages.error(request, f"Username '{new_username}' is already taken.")
                else:
                    target_user.username = new_username

            target_user.email = request.POST.get("email") or target_user.email
            password = request.POST.get("password")

            if password:
                target_user.set_password(password)

            # Roles
            target_user.is_staff = bool(request.POST.get("is_staff"))
            target_user.is_superuser = bool(request.POST.get("is_superuser"))
            target_user.save()
            messages.success(request, f"User '{target_user.username}' updated successfully.")

        # Suspend or activate user
        elif action == "toggle_active" and target_user:
            target_user.is_active = not target_user.is_active
            target_user.save()
            state = "activated" if target_user.is_active else "suspended"
            messages.info(request, f"User '{target_user.username}' has been {state}.")

        # Delete user
        elif action == "delete" and target_user:
            username = target_user.username
            target_user.delete()
            messages.error(request, f"User '{username}' has been permanently deleted.")

        # Promote to staff
        elif action == "promote_staff" and target_user:
            target_user.is_staff = True
            target_user.save()
            messages.success(request, f"{target_user.username} promoted to Staff.")

        # Promote to superuser
        elif action == "promote_super" and target_user:
            if not request.user.is_superuser:
                messages.error(request, "Only superusers can promote others to superuser.")
            else:
                target_user.is_superuser = True
                target_user.is_staff = True
                target_user.save()
                messages.success(request, f"{target_user.username} promoted to Superuser.")

        # ⭐ Assign a course to a user
        elif action == "assign_course" and target_user:
            course_id = request.POST.get("course_id")
            if course_id:
                course = get_object_or_404(Course, id=course_id)
                CourseAssignment.objects.get_or_create(user=target_user, course=course)
                messages.success(request, f"{target_user.username} assigned to {course.title}.")
            else:
                messages.error(request, "Please select a course before assigning.")

        return redirect("academy_manager_users")

    # Context now includes courses for the assignment UI
    return render(request, "academy/manager/users.html", {
        "users": users,
        "courses": courses,
    })


@login_required
def add_question(request):
    if not request.user.is_superuser:
        return redirect('academy_dashboard')

    if request.method == "POST":
        q_form = QuestionForm(request.POST)
        c_formset = ChoiceFormSet(request.POST)

        if q_form.is_valid() and c_formset.is_valid():
            question = q_form.save()
            choices = c_formset.save(commit=False)

            # Save each choice and link it
            for c in choices:
                c.question = question
                c.save()

            messages.success(request, "Question created successfully.")
            return redirect("academy_manager_tools")


    else:
        q_form = QuestionForm()
        c_formset = ChoiceFormSet()

    return render(request, "academy/add_question.html", {
        "q_form": q_form,
        "c_formset": c_formset,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def create_course(request):
    from .forms import CourseForm

    if request.method == "POST":
        form = CourseForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Course created successfully.")
            return redirect("academy_manager_tools")
    else:
        form = CourseForm()

    return render(request, "academy/manager/add_course.html", {"form": form})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_courses(request):
    courses = Course.objects.all().order_by('title')
    return render(request, "academy/manager/manage_courses.html", {"courses": courses})


@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_course(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    course.delete()
    messages.success(request, "Course deleted successfully.")
    return redirect("academy_manage_courses")


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_modules(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    modules = Module.objects.filter(course=course).order_by('order')

    return render(request, "academy/manager/manage_modules.html", {
        "course": course,
        "modules": modules
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_module(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    course_id = module.course.id
    module.delete()

    messages.success(request, "Module deleted successfully.")
    return redirect("academy_manage_modules", course_id)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_lessons(request, module_id):
    module = get_object_or_404(Module, id=module_id)
    lessons = Lesson.objects.filter(module=module).order_by("order")

    return render(request, "academy/manager/manage_lessons.html", {
        "module": module,
        "lessons": lessons
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def delete_lesson(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)
    module_id = lesson.module.id
    lesson.delete()

    messages.success(request, "Lesson deleted successfully.")
    return redirect("academy_manage_lessons", module_id)


def edit_lesson_content(request, lesson_id):
    lesson = get_object_or_404(Lesson, id=lesson_id)

    # Extract YouTube ID safely
    video_id = ""
    url = lesson.video_url or ""

    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "watch?v=" in url:
        video_id = url.split("watch?v=")[1].split("&")[0]
    elif "youtube.com/watch?v=" in url:
        video_id = url.split("watch?v=")[1].split("&")[0]

    if request.method == "POST":
        lesson.title = request.POST.get("title")
        lesson.order = request.POST.get("order")
        lesson.image_url = request.POST.get("image_url")
        lesson.video_url = request.POST.get("video_url")
        lesson.content = request.POST.get("content")
        lesson.save()
        messages.success(request, "Lesson updated.")
        return redirect("academy_manage_lessons", lesson.module.id)

    return render(request, "academy/manager/edit_lesson_content.html", {
        "lesson": lesson,
        "video_id": video_id,
    })




@login_required
@user_passes_test(lambda u: u.is_superuser)
def add_module(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    if request.method == "POST":
        title = request.POST.get("title")
        description = request.POST.get("description", "")
        order = request.POST.get("order") or 1

        if not title:
            messages.error(request, "Module title is required.")
            return redirect("academy_add_module", course_id=course.id)

        Module.objects.create(
            course=course,
            title=title,
            description=description,
            order=order,
            slug=title.lower().strip().replace(" ", "-")
        )

        messages.success(request, f"Module '{title}' created successfully.")
        return redirect("academy_manage_modules", course_id=course.id)

    return render(request, "academy/manager/add_module.html", {
        "course": course
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def add_lesson(request, module_id):
    module = get_object_or_404(Module, id=module_id)

    # Suggest next order number
    suggested_order = module.lessons.count() + 1

    if request.method == "POST":
        title = request.POST.get("title")
        order = request.POST.get("order") or suggested_order
        video_url = request.POST.get("video_url") or ""
        image_url = request.POST.get("image_url") or ""   # NEW FIELD

        if not title:
            messages.error(request, "Lesson title is required.")
            return redirect("academy_add_lesson", module_id=module.id)

        Lesson.objects.create(
            module=module,
            title=title,
            order=order,
            content="",      # content edited later via the content editor
            video_url=video_url,
            image_url=image_url,   # NEW FIELD SAVED
        )

        messages.success(request, f"Lesson '{title}' created successfully.")
        return redirect("academy_manage_lessons", module_id=module.id)

    return render(
        request,
        "academy/manager/add_lesson.html",
        {
            "module": module,
            "suggested_order": suggested_order,
        },
    )


@superuser_required
def manager_driver_progress(request):
    from django.contrib.auth import get_user_model
    User = get_user_model()

    users = User.objects.filter(is_superuser=False).order_by("username")
    modules = Module.objects.all().order_by("course__order", "order")

    display_rows = []

    for user in users:
        for module in modules:
            mp = ModuleProgress.objects.filter(user=user, module=module).first()

            if mp:
                status = mp.status
                score = mp.score
                completed_at = mp.completed_at
            else:
                status = "not_started"
                score = None
                completed_at = None

            display_rows.append({
                "user": user,
                "module": module,
                "score": score,
                "status": status,
                "completed_at": completed_at,
            })

    return render(request, "academy/manager/driver_progress_all.html", {
        "rows": display_rows
    })



@login_required
def update_choice(request, choice_id):
    choice = get_object_or_404(Choice, id=choice_id)

    if request.method == "POST":
        choice.text = request.POST.get("text")
        choice.is_correct = "is_correct" in request.POST
        choice.save()

        messages.success(request, "Answer updated.")
        return redirect("academy_edit_question", question_id=choice.question.id)

    return HttpResponse(status=405)


@login_required
def delete_choice(request, choice_id):
    choice = get_object_or_404(Choice, id=choice_id)
    question_id = choice.question.id
    choice.delete()

    messages.warning(request, "Answer deleted.")
    return redirect("academy_edit_question", question_id=question_id)


@login_required
def add_choice(request, question_id):
    question = get_object_or_404(Question, id=question_id)

    if request.method == "POST":
        text = request.POST.get("text")
        is_correct = "is_correct" in request.POST

        if text.strip():
            Choice.objects.create(
                question=question,
                text=text,
                is_correct=is_correct
            )
            messages.success(request, "Answer added.")

        return redirect("academy_edit_question", question_id=question.id)

    return HttpResponse(status=405)


@login_required
@user_passes_test(lambda u: u.is_superuser)
def manage_questions(request):
    questions = Question.objects.all().order_by("id")
    return render(request, "academy/manager/manage_questions.html", {
        "questions": questions,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def import_questions(request):
    if request.method == "POST":
        module_id = request.POST.get("module_id")
        delete_existing = request.POST.get("delete_existing") == "on"
        uploaded_file = request.FILES.get("json_file")

        if not uploaded_file:
            messages.error(request, "No JSON file uploaded.")
            return redirect("academy_import_questions")

        # Load raw JSON
        try:
            data = json.load(uploaded_file)
        except json.JSONDecodeError:
            messages.error(request, "Invalid JSON format.")
            return redirect("academy_import_questions")

        # Validate module from form
        try:
            default_module = Module.objects.get(id=module_id)
        except Module.DoesNotExist:
            messages.error(request, "Module not found.")
            return redirect("academy_import_questions")

        # Delete existing questions if checkbox ticked
        if delete_existing:
            Question.objects.filter(module=default_module).delete()

        created_q = 0
        created_c = 0
        skipped = 0

        # ------------------------------------------------------------------
        # DETECT FORMAT TYPE
        # ------------------------------------------------------------------
        fixture_format = False
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            fixture_format = "model" in first and "fields" in first

        # ------------------------------------------------------------------
        # FORMAT A: Django fixture format
        # ------------------------------------------------------------------
        if fixture_format:
            question_map = {}  # map pk → created Question object

            for obj in data:
                model = obj.get("model")
                fields = obj.get("fields", {})

                # Create Question
                if model == "academy.question":
                    module = default_module

                    # If fixture specifies module override
                    mod_id = fields.get("module")
                    if mod_id:
                        module = Module.objects.filter(id=mod_id).first() or module

                    q = Question.objects.create(
                        module=module,
                        text=fields.get("text", ""),
                        order=fields.get("order", 1),
                        explanation=fields.get("explanation", "")
                    )
                    question_map[obj["pk"]] = q
                    created_q += 1

                # Create Choice
                elif model == "academy.choice":
                    q_pk = fields.get("question")
                    question = question_map.get(q_pk)

                    # If question doesn’t exist
                    if not question:
                        skipped += 1
                        continue

                    Choice.objects.create(
                        question=question,
                        text=fields.get("text", ""),
                        is_correct=fields.get("is_correct", False)
                    )
                    created_c += 1

        # ------------------------------------------------------------------
        # FORMAT B: Clean custom JSON format
        # ------------------------------------------------------------------
        else:
            for entry in data:
                # Must contain text + choices
                if "text" not in entry or "choices" not in entry:
                    skipped += 1
                    continue

                # Module override by slug
                module = default_module
                slug = entry.get("module_slug")
                if slug:
                    module = Module.objects.filter(slug=slug).first() or default_module

                q = Question.objects.create(
                    module=module,
                    text=entry["text"],
                    order=entry.get("order", 1),
                    explanation=entry.get("explanation", "")
                )
                created_q += 1

                # Add choices
                for ch in entry["choices"]:
                    Choice.objects.create(
                        question=q,
                        text=ch["text"],
                        is_correct=ch.get("is_correct", False)
                    )
                    created_c += 1

        # ------------------------------------------------------------------

        messages.success(
            request,
            f"Imported {created_q} questions and {created_c} choices. "
            f"Skipped {skipped}."
        )
        return redirect("academy_import_questions")

    modules = Module.objects.all()
    return render(request, "academy/manager/import_questions.html", {"modules": modules})


@superuser_required
def manager_assign(request):
    from django.contrib.auth.models import Group

    users = User.objects.all().order_by("username")
    groups = Group.objects.all().order_by("name")
    courses = Course.objects.all().order_by("title")

    if request.method == "POST":
        course_id = request.POST.get("course")
        user_id = request.POST.get("user")
        group_id = request.POST.get("group")

        course = get_object_or_404(Course, id=course_id)

        # Assign user
        if user_id:
            user = get_object_or_404(User, id=user_id)
            CourseAssignment.objects.get_or_create(user=user, course=course)
            messages.success(request, f"{user} assigned to {course}")

        # Assign group
        elif group_id:
            group = get_object_or_404(Group, id=group_id)
            CourseAssignment.objects.get_or_create(group=group, course=course)
            messages.success(request, f"Group '{group.name}' assigned to {course}")

        return redirect("academy_manager_assign")

    assignments = CourseAssignment.objects.select_related("user", "group", "course")

    return render(request, "academy/manager/assign.html", {
        "users": users,
        "groups": groups,
        "courses": courses,
        "assignments": assignments,
    })


@login_required
@user_passes_test(lambda u: u.is_superuser)
def edit_question(request, question_id):
    question = get_object_or_404(Question, id=question_id)

    if request.method == "POST":
        # Update question fields
        question.text = request.POST.get("text")
        question.order = request.POST.get("order") or question.order
        module_id = request.POST.get("module")

        if module_id:
            question.module = Module.objects.filter(id=module_id).first()

        question.save()
        messages.success(request, "Question updated successfully.")
        return redirect("academy_edit_question", question_id=question.id)

    modules = Module.objects.all().order_by("course__order", "order")
    choices = question.choices.all().order_by("id")

    return render(request, "academy/manager/edit_question.html", {
        "question": question,
        "modules": modules,
        "choices": choices,
    })

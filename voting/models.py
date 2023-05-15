import datetime
import uuid

from django.db import models
from django.db.models import Q
from django.conf import settings
from django.db.models.query import QuerySet
from django.urls import reverse
from phonenumber_field.modelfields import PhoneNumberField
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

# now = datetime.datetime.now()
time  = timezone.now() + datetime.timedelta(hours=1)
now = time.time()


class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        """ Creates and save new user(voter)"""
        if not email:
            raise ValueError("Email address is required")

        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save()

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """ creates superuser"""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model """
    email = models.EmailField(
        verbose_name="email address", max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=True) #sign up required for only admin 
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    phone_number = PhoneNumberField(blank=True)
    is_deleted = models.BooleanField(default=False)

    objects = UserManager()

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "email"

    @property
    def is_admin(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_staff

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'


class Poll(models.Model):

    class PollObjects(models.Manager):
        def get_queryset(self) -> QuerySet:
            return super().get_queryset().filter(
                Q(start_time__lte=now) & Q(
                    end_time__gte=now) & Q(is_deleted=False)
            )

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True)
    start_time = models.TimeField(
        default=datetime.time(8, 0))  # poll starts at 8:00am
    end_time = models.TimeField(
        default=datetime.time(16, 0))  # poll ends at 4:00pm
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(auto_now=True)
    date_created = models.DateTimeField(auto_now_add=True)
    last_updated = models.DateTimeField(auto_now=True)

    objects = models.Manager()  # default manager
    pollobjects = PollObjects()  # custom 
    
    class Meta:
        ordering = ["-start_time", "name"]


    def __str__(self):
        return self.name

    @property
    def is_active(self):
        """ check if poll is active at current time """
        if self.start_time <= datetime.datetime.now().time() <= self.end_time:
            return True
        return False

    def get_absolute_url(self):
        return reverse("voting:poll-detail", args=(str(self.id)))

    def get_total_vote(self):
        return self.poll_votes.count()
    
    
class Candidate(models.Model):
    name = models.CharField(max_length=100, unique=True)
    image = models.ImageField(upload_to="e_voting/candidates", null=True, blank=True)
    poll = models.ForeignKey(
        Poll, on_delete=models.CASCADE, null=True, related_name="candidates")

    def __str__(self):
        return self.name

    def get_vote_count(self):
        return self.candidate_votes.count()


class Voter(models.Model):
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(verbose_name="email address", max_length=255, unique=True)
    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)
    phone_number = PhoneNumberField(blank=True)
    poll = models.ForeignKey(
        Poll, on_delete=models.CASCADE, related_name="voters")
    is_voted = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(auto_now=True)
    date_created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'

    def cast_vote(self):
        if not self.is_voted:
            self.is_voted = True
            self.save()
            return True
        return False
    

class Vote(models.Model):
    poll = models.ForeignKey(
        Poll, on_delete=models.CASCADE, related_name="poll_votes")
    candidate = models.ForeignKey(
        Candidate, on_delete=models.CASCADE, related_name="candidate_votes")
    voted_by = models.ForeignKey(Voter, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("poll", "voted_by")

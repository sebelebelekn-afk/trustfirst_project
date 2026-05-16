from django.contrib.auth.models import AbstractUser, Group, Permission
from django.db import models

class User(AbstractUser):
    # Verification badges
    VERIFIED = 'blue'
    CREATOR = 'white'
    INFLUENCER = 'gold'

    BADGE_CHOICES = [
        (VERIFIED, 'Verified'),
        (CREATOR, 'Creator'),
        (INFLUENCER, 'Influencer'),
    ]

    is_verified = models.BooleanField(default=False)
    badge = models.CharField(max_length=10, choices=BADGE_CHOICES, blank=True, null=True)
    is_kid = models.BooleanField(default=False)
    parent_email = models.EmailField(blank=True, null=True)

    # Fix reverse accessor clash
    groups = models.ManyToManyField(
        Group,
        related_name='custom_user_set',  # <- this avoids clash
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups'
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='custom_user_permissions_set',  # <- this avoids clash
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions'
    )

    def __str__(self):
        return self.username


class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='posts')
    video = models.FileField(upload_to='videos/')
    caption = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    likes = models.ManyToManyField(User, related_name='liked_posts', blank=True)
    bookmarks = models.ManyToManyField(User, related_name='bookmarked_posts', blank=True)

    # Flags for moderation / AI check
    is_ai_generated = models.BooleanField(default=False)
    is_kid_safe = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.author.username} - {self.caption[:20]}"

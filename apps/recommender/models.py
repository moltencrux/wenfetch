from django.db import models
from django.contrib.auth.models import User

class FreqEntry(models.Model):
    """Corpus word frequency table, loaded from freq.tsv."""
    word = models.CharField(max_length=50, unique=True, db_index=True)
    frequency = models.IntegerField()

    class Meta:
        verbose_name_plural = "freq entries"

    def __str__(self):
        return f"{self.word} ({self.frequency})"


class ArticleToken(models.Model):
    """Pre-segmented tokens for each scraped article."""
    article_key = models.CharField(max_length=16, db_index=True)
    source = models.CharField(max_length=200, db_index=True)
    token = models.CharField(max_length=50, db_index=True)

    class Meta:
        unique_together = ("article_key", "token")
        indexes = [
            models.Index(fields=["token", "article_key"]),
        ]

    def __str__(self):
        return f"{self.article_key}: {self.token}"


class VocabList(models.Model):
    """A named vocabulary list belonging to a user."""
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name="vocab_lists")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "name")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} / {self.name}"


class VocabEntry(models.Model):
    """A single word in a vocabulary list."""
    vocab_list = models.ForeignKey(VocabList, on_delete=models.CASCADE,
                                   related_name="entries")
    word = models.CharField(max_length=50, db_index=True)

    class Meta:
        unique_together = ("vocab_list", "word")

    def __str__(self):
        return self.word

class UserProfile(models.Model):  # or just add to User via OneToOne if simple
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    preferred_script = models.CharField(
        max_length=20,
        choices=[('simplified', 'Simplified First'), ('traditional', 'Traditional First')],
        default='traditional'  # or whatever your current default is
    )

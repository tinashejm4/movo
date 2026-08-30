from django.db import models

from apps.users.models import Biker

# Create your models here.
class BikerDailySession(models.Model):
    biker = models.ForeignKey(Biker, on_delete=models.CASCADE, related_name='daily_sessions')
    date = models.DateField()
    start_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    end_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('biker', 'date')

    def __str__(self):
        return f'{self.biker.user.username} - {self.date}'
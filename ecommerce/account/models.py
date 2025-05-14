from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class UserProfile(models.Model):
   
    profile_picture = models.ImageField(upload_to='images/', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return  f'{self.user}'
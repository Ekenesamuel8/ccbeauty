from django.contrib import admin

from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "has_profile_picture")
    search_fields = ("user__username", "user__email")
    list_select_related = ("user",)

    @admin.display(boolean=True, description="Profile picture")
    def has_profile_picture(self, obj):
        return bool(obj.profile_picture)

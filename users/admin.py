from django.contrib import admin
from django.utils.html import format_html
from .models import User, Profile, UserAnimeList, OneTimeCode

@admin.register(UserAnimeList)
class UserAnimeListAdmin(admin.ModelAdmin):
    list_display = ("user", "material", "status", "updated_at")
    list_filter  = ("status", "user")
    search_fields = (
        "user__username",
        "material__kodik_id",
        "material__slug",
        "material__title",
    )
    raw_id_fields = ("user", "material")


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "username", "email", "role", "is_active", "is_staff")
    search_fields = ("username", "email")
    list_filter = ("role", "is_active", "is_staff")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("id", "user_link", "display_name", "level_display", "xp", "progress_percent")
    search_fields = ("user__username", "display_name", "user__email")
    readonly_fields = ("level_display", "progress_percent_readonly")
    list_select_related = ("user",)
    actions = ("add_xp_10", "add_xp_100", "add_xp_1000")

    fieldsets = (
        (None, {
            "fields": ("user", "display_name", "bio", "avatar")
        }),
        ("Уровень", {
            "fields": ("xp", "level_display", "progress_percent_readonly")
        }),
        ("Служебное", {
            "fields": ()
        }),
    )

    def user_link(self, obj):
        return format_html('<strong>@{}</strong>', obj.user.username)
    user_link.short_description = "Пользователь"

    def level_display(self, obj):
        return obj.level
    level_display.short_description = "Уровень"

    def progress_percent(self, obj):
        return f"{round(obj.progress * 100)}%"
    progress_percent.short_description = "Прогресс"

    def progress_percent_readonly(self, obj):
        return self.progress_percent(obj)
    progress_percent_readonly.short_description = "Прогресс к след. уровню"

    @admin.action(description="Выдать +10 XP")
    def add_xp_10(self, request, queryset):
        for p in queryset:
            p.add_xp(10)

    @admin.action(description="Выдать +100 XP")
    def add_xp_100(self, request, queryset):
        for p in queryset:
            p.add_xp(100)

    @admin.action(description="Выдать +1000 XP")
    def add_xp_1000(self, request, queryset):
        for p in queryset:
            p.add_xp(1000)


@admin.register(OneTimeCode)
class OneTimeCodeAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "action", "value", "code", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("user__username", "user__email", "value", "code")
    ordering = ("-created_at",)

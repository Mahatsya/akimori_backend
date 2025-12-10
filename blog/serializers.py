from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import Category, Tag, Post

User = get_user_model()


class CategorySerializer(serializers.ModelSerializer):
    posts_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Category
        fields = ("id", "slug", "name", "posts_count")


class TagSerializer(serializers.ModelSerializer):
    posts_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Tag
        fields = ("id", "slug", "name", "posts_count")


class AuthorShortSerializer(serializers.ModelSerializer):
    # в ответе: { id, username, display_name }
    display_name = serializers.CharField(source="first_name", allow_null=True, required=False)

    class Meta:
        model = User
        fields = ("id", "username", "display_name")


class PostBaseSerializer(serializers.ModelSerializer):
    author = AuthorShortSerializer(read_only=True)
    categories = CategorySerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    # входные поля для записи M2M
    category_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = Post
        fields = (
            "id", "slug", "title", "excerpt",
            "content_html", "poster",
            "pinned", "is_closed", "status",
            "published_at", "created_at", "updated_at",
            "author", "categories", "tags",
            "category_ids", "tag_ids",
        )
        read_only_fields = (
            "id", "slug", "published_at", "created_at", "updated_at", "author",
        )

    # разрешаем фронту слать старый ключ `content`, мапим его на content_html
    def _coerce_content(self, validated_data):
        raw = self.initial_data or {}
        if "content_html" not in validated_data and "content" in raw:
            validated_data["content_html"] = raw.get("content")

    def _assign_m2m(self, instance, validated_data):
        # если ключ передан — применяем (включая пустой список), если не передан — не трогаем
        if "category_ids" in validated_data:
            cat_ids = validated_data.pop("category_ids", [])
            instance.categories.set(Category.objects.filter(id__in=cat_ids))
        if "tag_ids" in validated_data:
            tag_ids = validated_data.pop("tag_ids", [])
            instance.tags.set(Tag.objects.filter(id__in=tag_ids))

    def create(self, validated_data):
        self._coerce_content(validated_data)
        request = self.context.get("request")
        author = request.user if request and request.user.is_authenticated else None

        # извлекаем m2m до сохранения
        cat_ids = validated_data.pop("category_ids", None)
        tag_ids = validated_data.pop("tag_ids", None)

        post = Post(**validated_data)
        if author:
            post.author = author
        post.save()

        # применяем m2m (None = не трогаем; [] = очистить)
        if cat_ids is not None:
            post.categories.set(Category.objects.filter(id__in=cat_ids))
        if tag_ids is not None:
            post.tags.set(Tag.objects.filter(id__in=tag_ids))
        return post

    def update(self, instance, validated_data):
        self._coerce_content(validated_data)
        # обычные поля
        cat_ids = validated_data.pop("category_ids", None)
        tag_ids = validated_data.pop("tag_ids", None)

        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        if cat_ids is not None:
            instance.categories.set(Category.objects.filter(id__in=cat_ids))
        if tag_ids is not None:
            instance.tags.set(Tag.objects.filter(id__in=tag_ids))
        return instance


class PostListSerializer(PostBaseSerializer):
    class Meta:
        model = Post
        fields = (
            "id","slug","title","excerpt","content_html","poster",
            "pinned","is_closed","status","published_at","created_at","updated_at",
            "author","categories","tags","category_ids","tag_ids",
        )
    read_only_fields = ("id","slug","published_at","created_at","updated_at","author")


class PostDetailSerializer(PostBaseSerializer):
    pass

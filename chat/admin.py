from django.contrib import admin
from unfold.admin import ModelAdmin
from .models import Conversation, Message, ChatBlock

@admin.register(Conversation)
class ConversationAdmin(ModelAdmin):
    list_display = ('id', 'created_at', 'updated_at')
    filter_horizontal = ('participants',)

@admin.register(Message)
class MessageAdmin(ModelAdmin):
    list_display = ('sender', 'conversation', 'is_seen', 'created_at')
    list_filter = ('is_seen', 'created_at')
    search_fields = ('sender__email', 'message')

@admin.register(ChatBlock)
class ChatBlockAdmin(ModelAdmin):
    list_display = ('blocker', 'blocked', 'conversation', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('blocker__email', 'blocked__email')
    raw_id_fields = ('blocker', 'blocked', 'conversation')


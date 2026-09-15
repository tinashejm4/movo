from django.core.management.base import BaseCommand

from apps.notifications.services import enqueue_pending_notification_outboxes


class Command(BaseCommand):
    help = "Enqueue pending notification outbox records for Celery delivery."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **options):
        count = enqueue_pending_notification_outboxes(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Enqueued {count} pending notification(s)."))

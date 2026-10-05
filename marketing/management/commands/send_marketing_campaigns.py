from django.core.management.base import BaseCommand

from marketing.models import MarketingCampaign
from marketing.services import process_campaign


class Command(BaseCommand):
    help = "Process queued/sending marketing campaigns (batch per campaign)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--campaign-id",
            type=int,
            default=None,
            help="Process only this campaign id.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=50,
            help="Max recipients to send per campaign run (default 50).",
        )

    def handle(self, *args, **options):
        batch_size = max(1, min(int(options["batch_size"] or 50), 500))
        campaign_id = options.get("campaign_id")
        qs = MarketingCampaign.objects.filter(
            status__in=[
                MarketingCampaign.Status.QUEUED,
                MarketingCampaign.Status.SENDING,
            ]
        ).order_by("id")
        if campaign_id:
            qs = qs.filter(pk=campaign_id)

        total = 0
        for campaign in qs:
            counts = process_campaign(campaign.id, batch_size=batch_size)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Campaign {campaign.id}: sent={counts['sent']} "
                    f"failed={counts['failed']} skipped={counts['skipped']}"
                )
            )
            total += counts["sent"] + counts["failed"] + counts["skipped"]

        self.stdout.write(self.style.SUCCESS(f"Processed {total} recipients."))

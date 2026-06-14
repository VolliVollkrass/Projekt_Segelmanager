from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = 'Sendet eine Test-E-Mail zur Überprüfung des Mail-Backends'

    def add_arguments(self, parser):
        parser.add_argument('empfaenger', type=str, help='Empfänger-Adresse')

    def handle(self, *args, **options):
        empfaenger = options['empfaenger']
        self.stdout.write(f'Sende Test-Mail an {empfaenger} ...')
        self.stdout.write(f'Backend: {settings.EMAIL_BACKEND}')
        self.stdout.write(f'From:    {settings.DEFAULT_FROM_EMAIL}')

        send_mail(
            subject='Meer erleben — Test-E-Mail',
            message='Diese E-Mail bestätigt, dass der Mailversand korrekt konfiguriert ist.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[empfaenger],
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS('Mail erfolgreich gesendet (oder im Terminal ausgegeben).'))

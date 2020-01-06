'''
    Copyright (C) 2018 Gitcoin Core

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program. If not, see <http://www.gnu.org/licenses/>.

'''
from django.conf import settings
from django.core.management.base import BaseCommand
from dashboard.models import Profile
from chat.tasks import create_user
import logging
from celery import group

logger = logging.getLogger(__name__)

from marketing.utils import should_suppress_notification_email


class Command(BaseCommand):
    help = "create users to Gitcoin chat, creates the user if it doesn't exist"

    def handle(self, *args, **options):
        try:

            users = Profile.objects.filter(user__is_active=True).prefetch_related('user')

            tasks = []

            for profile in users:
                # if profile.chat_id is None:
                tasks.append(create_user.si(options={
                    "email": profile.user.email,
                    "username": profile.handle,
                    "first_name": profile.user.first_name,
                    "last_name": profile.user.last_name,
                    "nickname": profile.handle,
                    "auth_data": f'{profile.user.id}',
                    "auth_service": "gitcoin",
                    "locale": "en",
                    "props": {},
                    "notify_props": {
                        "email": "false" if should_suppress_notification_email(profile.user.email, 'chat') else "true",
                        "push": "mention",
                        "desktop": "all",
                        "desktop_sound": "true",
                        "mention_keys": f'{profile.handle}, @{profile.handle}',
                        "channel": "true",
                        "first_name": "false"
                    },
                }, params={
                    "tid": settings.GITCOIN_HACK_CHAT_TEAM_ID
                }))
            job = group(tasks)

            result = job.apply_async()
            for r in result.get():
                if r is not None:
                    if 'username' in r and 'id' in r:
                        profile = Profile.objects.filter(handle=r['username'])[0]
                        if profile is not None:
                            profile.chat_id = r['id']
                            profile.save()

        except ConnectionError as exec:
            print(str(exec))
            self.retry(30)
        except Exception as e:
            logger.error(str(e))
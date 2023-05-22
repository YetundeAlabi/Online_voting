from django.contrib import admin
from voting.models import Poll, Candidate, Voter
# Register your models here.
admin.site.register(Poll)
admin.site.register(Candidate)
admin.site.register(Voter)
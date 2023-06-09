from typing import Any
import csv
import smtplib
from datetime import datetime, timedelta

from django.forms.models import BaseModelForm
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render, redirect
from django.http import Http404
from django.contrib.sites.shortcuts import get_current_site
from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.views.generic import ListView, DetailView, View
from django.views.generic.edit import CreateView,UpdateView
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import authenticate, login, logout
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.contrib import messages
from django.core.mail import send_mail
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.decorators.csrf import csrf_protect
from django.db.models import Count, Max
from urllib.parse import urlencode, unquote

from .forms import VoterUploadForm, PollForm
from voting.models import Poll, Voter, Candidate, Vote


now = timezone.now().time()


def custom_404(request, exception):
    return render(request, '404.html', status=404)

@csrf_protect
def login_view(request):
    if request.method == "POST":
        email = request.POST["email"]
        password = request.POST["password"]
        user = authenticate(request, email=email, password=password)
        print(user)
        if user is not None:
            login(request, user)
            messages.info(request, f"You are now logged in as {email}.")
            return redirect("voting:poll-list")
        else:
            messages.error(request,"Invalid username or password.")
            return render(request, 'voting/login.html', {'error': 'Invalid credentials'})		
    return render(request, "voting/login.html")



def logout_view(request):
    logout(request)
    return redirect("voting:login")

 

class SignupView(CreateView):
    template_name = 'voting/signup.html'
    form_class = UserCreationForm
    success_url = reverse_lazy('login')


class PollListView(LoginRequiredMixin, ListView):
    model = Poll
    template_name = "voting/poll_list.html"


class PollDetailView(LoginRequiredMixin, DetailView):
    model = Poll
    template_name = 'voting/poll_detail.html'


class PollCreateView(LoginRequiredMixin, CreateView):
    model = Poll
    template_name = "voting/poll_form.html"
    form_class = PollForm
    # fields = ["name", "description","start_time", "end_time"]


class PollUpdateView(LoginRequiredMixin, UpdateView):
    model = Poll
    template_name = 'voting/poll_update.html'
    fields = ['start_time', 'end_time']

    def get_object(self, queryset=None):
        obj = get_object_or_404(Poll, pk=self.kwargs['pk'])
        return obj

    def form_valid(self, form):
        poll = form.save(commit=False)
        # Check if the poll has started
        # Check if the poll is active
        if poll.is_active:
            # If poll is active, update only the end time
            poll.end_time = form.cleaned_data['end_time'] 
        else:
            # If poll is not active, update both start time and end time
            poll.start_time = form.cleaned_data['start_time']
            poll.end_time = form.cleaned_data['end_time']
            if now > poll.start_time:
                raise ValidationError("Poll has already started. Start time can not be updated") 

        poll.save()
        return redirect('voting:poll-list')


class PollDeleteView( LoginRequiredMixin, UpdateView):
    model = Poll
    template_name = 'poll_delete.html'
    fields = []

    def get_object(self, queryset=None):
        obj = get_object_or_404(Poll, pk=self.kwargs['pk'])
        return obj

    def form_valid(self, form):
        poll = form.save(commit=False)
        poll.is_deleted = True
        poll.save()
        return redirect('voting:poll-list')


class CandidateCreateView(LoginRequiredMixin, CreateView):
    model = Candidate
    fields = ["name"]

    def post(self, request, *args, **kwargs):
        # queryset = Candidate.objects.filter(poll_id=self.kwargs["pk"])
        poll = Poll.objects.get(id=self.kwargs["pk"])
        name = request.POST.get("name")
        candidate = Candidate.objects.create(name=name, poll=poll)
        candidate.save()
        messages.info(self.request, f"Candidate succesfully added to {poll.name}.")
        return redirect("voting:poll-list")

    def get_success_url(self) -> str:
        return reverse_lazy("voting:poll-list")


class CandidateListView(LoginRequiredMixin, ListView):
    model = Candidate
    template_name = "voting/poll_detail.html"

    def get_queryset(self):
        return Candidate.objects.filter(poll_id=self.kwargs["pk"])


class VoterCreateView(LoginRequiredMixin, CreateView):
    model = Voter
    fields = ["email", "first_name", "last_name", "phone_number"]

    def post(self, request, *args, **kwargs):
        # queryset = Candidate.objects.filter(poll_id=self.kwargs["pk"])
        poll = Poll.objects.get(id=self.kwargs["pk"])
        voter_data = {
            "email": request.POST.get("email"),
            "first_name": request.POST.get("first_name"),
            "last_name": request.POST.get("last_name"),
            "phone_number": request.POST.get("phone_number")
        }
        voter = Voter.objects.create(**voter_data, poll=poll)
        voter.save()
        messages.info(self.request, f"Voter succesfully added to {poll.name}.")
        return redirect("voting:poll-list")

    def form_valid(self, form):
        voter = form.save(commit=False)
        if voter.poll.is_active:
            messages.error(self.request,"This poll has started. You can't add new voters.")
            return redirect('voting:poll-list')
        else:
            voter.save()
            messages.info(self.request, "succesful.")
            return redirect("voting:poll-list")

    def get_success_url(self):
        return reverse_lazy("voting:poll-list")
    
    
class VoterDeleteView(View):

    def get(self, request, *args, **kwargs):
        queryset = Voter.objects.filter(poll=kwargs["pk"])
        voter = get_object_or_404(queryset, pk=kwargs['voter_pk'])

        # if voter.poll.is_active:
        #     raise Http404("Cannot delete a voter on an active poll")
        
        voter.is_deleted = True
        voter.save()
        return redirect('voting:poll-list')


class SendEmailView(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        voters = Voter.objects.filter(poll_id=self.kwargs["pk"])
        poll_id = self.kwargs["pk"]
        poll = Poll.objects.get(id=poll_id)
        # .values_list("email", flat=True)
        
        current_site = get_current_site(request).domain
        
        for voter in voters:
            # poll_id = voter.poll.id
            voter_id = voter.uuid
            voter_email = voter.email
            poll_link = reverse('voting:vote', args=[poll_id, voter_id])
            voter_link = urlencode({'url': poll_link}) 
            # Send the poll email to the voter
            try:
                send_mail(
                    subject='Poll Notification',
                    message=f'Please participate in the poll. Click the link below:\n\n{current_site}{poll_link}',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[voter_email],
                    
                )
                messages.info(self.request, f"Email Notification for {poll.name} poll in progress....") 
            except smtplib.SMTPException as e:
                messages.error(self.request, "An SMTP error occured")
                print(f"An error occured: {e}")


            finally:
                Voter.objects.values_list("email", flat=True).update(email_sent=True)
        messages.info(self.request, f"Poll Notification for {poll.name} sent successfully.")
        return redirect(reverse_lazy("voting:poll-list"))
    

def vote_success(request):
    return render(request, 'voting/vote-success.html')
     

class VoteView(View):

    def post(self, request, *args, **kwargs):
        voter = get_object_or_404(Voter, pk=kwargs['voter_pk'])
        poll = voter.poll
        
        try:
            selected_candidate = poll.candidates.get(pk=request.POST.get("candidate"))

        except (KeyError, Candidate.DoesNotExist):
            return render(
                request,
                "voting/vote_form.html",
                {
                    "poll": poll,
                    "error_message": "You didn't select a candidate.",
                },
            )

        if Vote.objects.filter(poll=poll, voted_by=voter).exists():
            return render(request, "voting/already_voted.html")
        
        vote = Vote(poll=poll, candidate=selected_candidate, voted_by=voter)
        vote.save()
        voter.cast_vote()

        # return redirect('voting:vote-success')
        return redirect('voting:vote-success')
    
    
    def get(self, request, *args, **kwargs):
        try:
            time  = timezone.now() + timedelta(hours=1)
            now = time.time()
            print(now)
            voter = Voter.objects.get(pk=kwargs["voter_pk"])
            poll = voter.poll
            candidates = poll.candidates.all()
            context = {
                'poll': poll,
                'voter': voter,
                'candidates': candidates,
                "now": now
            }
            return render(request, 'voting/vote_form.html', context)

        except Voter.DoesNotExist:
            raise Http404("Voter not found.")
    

class VoterImportView(LoginRequiredMixin, View):
    template_name = 'voter/import_voters.html'

    def get(self, request, pk):
        form = VoterUploadForm
        return render(request, 'voting/import_voters.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = VoterUploadForm
        poll_id = kwargs.get("pk")
        poll = get_object_or_404(Poll, id=poll_id)

        # Check if the poll is active
        if poll.is_active:
            error_message = "Cannot import voters when the poll is active."
            messages.error(request,  "This poll is still active")
            return render(request, 'voting/import_voters.html', {'form': VoterUploadForm, 'error': error_message})

        try:
            csv_file = request.FILES['csv_file']
            decoded_file = csv_file.read().decode('utf-8')
            csv_data = csv.DictReader(decoded_file.splitlines(), delimiter=',')
            expected_headers = ["email", "first_name", "last_name", "phone_number"]
            headers = csv_data.fieldnames
            print(headers)  
            if headers != expected_headers:
                raise ValueError('Invalid CSV file. Headers do not match. Expected headers: {}'.format(', '.join(expected_headers)))
            
            with transaction.atomic():
                for row in csv_data:
                    try:
                        Voter.objects.create(poll=poll, first_name=row["first_name"], last_name=row["last_name"],
                                        email=row['email'], phone_number=row['phone_number'])
                    except IntegrityError:
                        transaction.rollback()
                        messages.error(
                            request, f"Error! Error!!"
                        )
                        return HttpResponseRedirect(reverse("voting:poll-detail"))
                    
                messages.success(request, "Import successful")
                return redirect('voting:poll-list')  # Redirect to poll detail page after successful upload
        except csv.Error as e:
            messages.error(request, f"Error processing CSV file: {e}")
            
        return render(request, 'voting/import_voters.html', {'form': form})


class PollResultView(View):

    def get(self, request, *args, **kwargs):

        poll = Poll.objects.get(pk=self.kwargs["pk"])
        # Retrieve all the votes for the poll
        votes = Vote.objects.filter(poll=poll)
        
        candidates = poll.candidates.all()
        candidate_votes = votes.values('candidate').annotate(total_votes=Count('candidate'))

        # Find the highest number of votes
        highest_votes = candidate_votes.aggregate(max_votes=Max('total_votes'))['max_votes']

        # Find the candidates with the highest number of votes
        winners = candidate_votes.filter(total_votes=highest_votes).values_list('candidate', flat=True)

        # Retrieve the candidate objects
        winning_candidates = Candidate.objects.filter(pk__in=winners)

        context = {
            'poll': poll,
            'winning_candidates': winning_candidates,
            'total_votes': votes.count(),
            'candidates': candidates,
        }
        return render(request, 'voting/poll_results.html', context)


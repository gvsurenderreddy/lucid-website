from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render_to_response
from desktopsite.apps.repository.models import *
from desktopsite.apps.repository.categories import REPOSITORY_CATEGORIES

def index(request):
    return render_to_response('repository/index.html', {
        'categories': REPOSITORY_CATEGORIES                                                    
    })
    
def byLetter(request, letter):
    results = Package.objects.filter(name__startswith=letter)
    return showResults(request, "Packages starting with \"%s\"" % letter, results)
    
def byCategory(request, category):
    results = Package.objects.filter(category__exact=category)
    return showResults(request, "Packages in \"%s\"" % category, results)
    
def search(request):
    query = request.GET["q"]
    results = Package.objects.filter(name__contains=query)
    return showResults(request, "Results for \"%s\"" % query, results)
    
def showResults(request, title, resultset):
    return render_to_response('repository/results.html', {
        'results': resultset,
        'title': (title if title else "Search Results"),
    })
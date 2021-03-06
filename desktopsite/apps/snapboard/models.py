import sets
from datetime import datetime

from django.conf import settings
from django.contrib.auth.models import User, Group
from django.db import models
from django.db.models import signals
from django.dispatch import dispatcher

from fields import PhotoField
from middleware import threadlocals

import managers

from django.contrib import admin

SNAP_PREFIX = getattr(settings, 'SNAP_PREFIX', '/snapboard')
SNAP_MEDIA_PREFIX = getattr(settings, 'SNAP_MEDIA_PREFIX', 
        getattr(settings, 'MEDIA_URL', '') + '/media')
SNAP_LOGIN_URL = SNAP_PREFIX + '/signin'


class Category(models.Model):
    label = models.CharField(max_length=32)

    objects = managers.CategoryManager()    # adds thread_count

    def __str__(self):
        return self.label

    def moderators(self):
        mods = Moderator.objects.filter(category=self.id)
        if mods.count() > 0:
            return ', '.join([m.user.username for m in mods])
        else:
            return None

    class Meta:
        verbose_name_plural = 'categories'

    class Admin:
        pass
admin.site.register(Category)

class Moderator(models.Model):
    category = models.ForeignKey(Category)
    user = models.ForeignKey(User)


class Thread(models.Model):
    subject = models.CharField(max_length=160)
    category = models.ForeignKey(Category)

    closed = models.BooleanField(default=False)

    # Category sticky - will show up at the top of category listings.
    csticky = models.BooleanField(default=False)

    # Global sticky - will show up at the top of home listing.
    gsticky = models.BooleanField(default=False)

    objects = models.Manager() # needs to be explicit due to below
    view_manager = managers.ThreadManager()

    def __str__(self):
        return self.subject

    def get_url(self):
        return SNAP_PREFIX + '/threads/id/' + self.id + '/'

    class Admin(admin.ModelAdmin):
        list_display = ('subject', 'category')
        list_filter = ('closed', 'csticky', 'gsticky', 'category')

admin.site.register(Thread, Thread.Admin)

class ThreadInline(admin.StackedInline):
        model = Thread
        max_num = 1

class Post(models.Model):
    """
    Post objects store information about revisions.

    Both forward and backward revisions are stored as ForeignKeys.
    """
    # blank=True to get admin to work when the user field is missing
    user = models.ForeignKey(User, editable=False, blank=True, default=None)

    thread = models.ForeignKey(Thread)
    text = models.TextField()
    date = models.DateTimeField(editable=False,auto_now_add=True)
    ip = models.IPAddressField(blank=True)

    private = models.ManyToManyField(User,
            related_name="private_recipients", null=True)

    # (null or ID of post - most recent revision is always a diff of previous)
    odate = models.DateTimeField(editable=False, null=True)
    revision = models.ForeignKey("self", related_name="rev",
            editable=False, null=True, blank=True)
    previous = models.ForeignKey("self", related_name="prev",
            editable=False, null=True, blank=True)

    # (boolean set by mod.; true if abuse report deemed false)
    censor = models.BooleanField(default=False) # moderator level access
    freespeech = models.BooleanField(default=False) # superuser level access


    objects = models.Manager() # needs to be explicit due to below
    view_manager = managers.PostManager()

    def save(self):
        #print 'user =', threadlocals.get_current_user()
        #print threadlocals.get_current_ip(), type(threadlocals.get_current_ip())

        # hack to disallow admin setting arbitrary users to posts
        if getattr(self, 'user_id', None) is None:
            self.user_id = threadlocals.get_current_user().id

        # disregard any modifications to ip address
        self.ip = threadlocals.get_current_ip()
        # self.ip = '127.0.0.1'

        if self.previous is not None:
            self.odate = self.previous.odate
        elif not self.id:
            # only do the following on creation, not modification
            self.odate = datetime.now()
        super(Post, self).save()


    def management_save(self):
        if self.previous is not None:
            self.odate = self.previous.odate
        elif not self.id:
            # only do the following on creation, not modification
            self.odate = datetime.now()
        super(Post, self).save()


    def get_absolute_url(self):
        return ''.join(('/forum/threads/id/', str(self.thread.id), '/#post', str(self.id)))

    def get_edit_form(self):
        from forms import PostForm
        return PostForm(initial={'post':self.text})

    def __str__(self):
        return ''.join( (str(self.user), ': ', str(self.date)) )

    class Admin(admin.ModelAdmin):
        list_display = ('user', 'date', 'thread', 'ip')
        list_filter    = ('censor', 'freespeech', 'user',)
        search_fields  = ('text', 'user')
        inlines = [ThreadInline]
        
admin.site.register(Post, Post.Admin)

# class PostAdminOptions(models.options.AdminOptions):
#     '''
#     Replaces AdminOptions for Post model
#     '''
#     def _fields(self):
#         user = threadlocals.get_current_user()
#         assert(not(user is None or user.is_anonymous()))
# 
#         if user.has_perm('moderator.superuser'):
#             pass
#         else:
#             pass
#     fields = property(_fields)
# 
# # register PostAdminOptions
# #del Post._meta.admin.fields
# #Post._meta.admin.__class__ = PostAdminOptions


class AbuseReport(models.Model):
    '''
    When an abuse report is filed by a registered User, the post is listed
    in this table.

    If the abuse report is rejected as false, the post.freespeech flag can be
    set to disallow further abuse reports on said thread.
    '''
    post = models.ForeignKey(Post)
    submitter = models.ForeignKey(User)
    class Admin(admin.ModelAdmin):
        list_display = ('post', 'submitter')

    class Meta:
        unique_together = (('post', 'submitter'),)
admin.site.register(AbuseReport, AbuseReport.Admin)

class WatchList(models.Model):
    """
    Keep track of who is watching what thread.  Notify on change (sidebar).
    """
    user = models.ForeignKey(User)
    thread = models.ForeignKey(Thread)
    # no need to be in the admin


class UserInline(admin.StackedInline):
        model = User
        max_num = 1

class SnapboardProfile(models.Model):
    '''
    User data tied to user accounts from the auth module.

    Real name, email, and date joined information are stored in the built-in
    auth module.

    After logging in, save these values in a session variable.
    '''
    user = models.ForeignKey(User, unique=True, editable=False)
    profile = models.TextField(blank=True)

    avatar = PhotoField(blank=True, upload_to='img/snapboard/avatars/',
            width=24, height=24)

    # browsing options
    ppp = models.IntegerField(
            choices = ((5, '5'), (10, '10'), (20, '20'), (50, '50')),
            default = 20,
            help_text = "Posts per page")
    tpp = models.IntegerField(
            choices = ((5, '5'), (10, '10'), (20, '20'), (50, '50')),
            default = 20,
            help_text = "Threads per page")
    notify_email = models.BooleanField(default=False, blank=True,
            help_text = "Email notifications for watched discussions.")
    reverse_posts = models.BooleanField(
            default=False,
            help_text = "Display newest posts first.")
    frontpage_filters = models.ManyToManyField(Category,
            null=True, blank=True,
            help_text = "Filter your front page on these categories.")
    
    def get_number_of_posts(self):
        return Post.objects.filter(user=self.user).count()

    ## edit inline
    class Admin(admin.ModelAdmin):
        list_display = ('user', 'ppp', 'tpp', 'notify_email')
        fieldsets = (
            (None, 
                {'fields': ('avatar',)}),
            ('Profile', 
                {'fields': ('profile',)}),
            ('Browsing Options', 
                {'fields': 
                    ('ppp', 'tpp', 'notify_email', 'reverse_posts', 'frontpage_filters',)}),
        )
        inlines=[UserInline]

admin.site.register(SnapboardProfile, SnapboardProfile.Admin)

# TODO: perhaps this should be placed in another application
class BannedUser(models.Model):
    '''
    This is a login-level ban.  These users will be able to browse the board
    but will not be able to log in.
    '''
    user = models.ForeignKey(User, unique=True)
    reason = models.TextField()
    def __str__(self):
        return str(self.user)

    class Admin:
        pass

admin.site.register(BannedUser)

class BannedIP(models.Model):
    '''
    Each line should have an IP address.
    
    The objects in this model are not allowed to log in or register new
    accounts.
    '''

    iplist = models.IPAddressField()
    reason = models.TextField()

    def get_ips(self):
        return [i.strip() for i in str(self.iplist).splitlines()]

    def __str__(self):
        return ','.join(self.get_ips())

    class Admin:
        pass

admin.site.register(BannedIP)

def update_ban_cache(**kwargs):
    ips = []
    users = [int(u.id) for u in BannedUser.objects.all()]

    for ip in BannedIP.objects.all():
        ips.extend(ip.get_ips())

    settings.SNAP_BANNED_IPS = sets.Set(ips)
    settings.SNAP_BANNED_USERS = sets.Set(users)

signals.post_save.connect(update_ban_cache, sender=BannedIP)
signals.post_delete.connect(update_ban_cache, sender=BannedIP)
signals.post_save.connect(update_ban_cache, sender=BannedUser)
signals.post_delete.connect(update_ban_cache, sender=BannedUser)


# from django.contrib.site.models import Site
# def watched_thread_notify(instance):
#     thread_id = instance.thread.id
#     watchlist = WatchList.objects.select_related().filter(thread__id=thread_id)
# 
#     site = Site.objects.get(pk=settings.SITE_ID)
# 
#     people = [w.user.email for w in watchlist]
#     subject_tmp = loader.get_template("tracker/watched_thread_notify_subject.txt")
#     body_tmp = loader.get_template("tracker/watched_thread_notify_body.txt")
# 
#     ctx = Context({'post':instance, 'site':site})
#     subject = subject_tmp.render(ctx).strip()
#     body = body_tmp.render(ctx)
# 
#     send_mail(subject, body, 'snapboard@'+site.domain, people)
# connect this handler
#dispatcher.connect(watched_thread_notify, sender=Post, signal=signals.post_save)

# vim: ai ts=4 sts=4 et sw=4

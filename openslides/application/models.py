#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    openslides.application.models
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Models for the application app.

    :copyright: 2011 by the OpenSlides team, see AUTHORS.
    :license: GNU GPL, see LICENSE for more details.
"""

from datetime import datetime

from django.db import models
from django.db.models import Max
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _

from openslides.system.api import config_get


class Application(models.Model):
    STATUS = (
        ('pub', _('Published')),
        ('per', _('Permitted')),
        ('acc', _('Accepted')),
        ('rej', _('Rejected')),
        ('wit', _('Withdrawed')),
        ('adj', _('Adjourned')),
        ('noc', _('Not Concerned')),
        ('com', _('Commited a bill')),
        ('nop', _('Rejected (not permitted)')),
        #additional actions:
        # edit
        # delete
        # setnumber
        # support
        # unsupport
        # createitem
        # genpoll
    )

    submitter = models.ForeignKey(User, verbose_name=_("Submitter"))
    supporter = models.ManyToManyField(User, related_name='supporter', \
                                       null=True, blank=True, verbose_name=_("Supporters"))
    number = models.PositiveSmallIntegerField(blank=True, null=True,
                                        unique=True)
    status = models.CharField(max_length=3, choices=STATUS, default='pub')
    permitted = models.ForeignKey('AVersion', related_name='permitted', \
                                  null=True, blank=True)
    log = models.TextField(blank=True, null=True)

    @property
    def last_version(self):
        """
        Return last version of the application.
        """
        try:
            return AVersion.objects.filter(application=self).order_by('id') \
                                   .reverse()[0]
        except IndexError:
            return None

    def accept_version(self, version):
        """
        accept a Version
        """
        if version.id > self.permitted.id:
            self.permitted = version
            self.save()
            return True
        return False

    def reject_version(self, version):
        if version.id > self.permitted.id:
            version.rejected = True
            version.save()
            return True
        return False

    @property
    def versions(self):
        """
        Return a list of all versions of the application.
        """
        return AVersion.objects.filter(application=self)

    @property
    def creation_time(self):
        """
        Return the time of the creation of the application.
        """
        try:
            return self.versions[0].time
        except IndexError:
            return None

    @property
    def notes(self):
        """
        Return some information of the application.
        """
        note = []
        if self.status == "pub" and not self.enough_supporters:
            note.append(_("Searching for supporters."))
        if self.status == "pub" and self.permitted is None:
            note.append(_("Not yet permitted."))
        elif self.unpermitted_changes and self.permitted:
            note.append(_("Not yet permitted changes."))
        return note

    @property
    def unpermitted_changes(self):
        """
        Return True if the application has unpermitted changes.

        The application has unpermitted changes, if the permitted-version
        is not the lastone and the lastone is not rejected.
        TODO: rename the property in unchecked__changes
        """
        if (self.last_version != self.permitted
        and not self.last_version.rejected):
            return True
        else:
            return False

    @property
    def enough_supporters(self):
        """
        Return True, if the application has enough supporters
        """
        min_supporters = int(config_get('application_min_supporters'))
        return self.supporter.count() >= min_supporters

    def save(self, user=None):
        """
        Save the Application, and create a new AVersion if necessary
        """
        super(Application, self).save()
        last_version = self.last_version
        if last_version is not None:
            if (last_version.text == self.text
            and last_version.title == self.title
            and last_version.reason == self.reason):
                return  # No changes
        try:
            if self.title != "":
                version = AVersion(title=getattr(self, 'title', ''),
                           text=getattr(self, 'text', ''),
                           reason=getattr(self, 'reason', ''),
                           application=self)
                version.save()
                self.writelog(_("Version %s created") % version.aid, user)
            is_manager = user.has_perm('application.can_manage_application')
        except AttributeError:
            is_manager = False

        if (self.status == "pub"
        and self.supporter.exists()
        and not is_manager):
            self.supporter.clear()
            self.writelog(_("Supporters removed"), user)

    def reset(self, user):
        """
        Reset the application.
        """
        self.status = "pub"
        self.permitted = None
        self.save()
        self.writelog(_("Status reseted to: %s") % (self.get_status_display()), user)

    def support(self, user):
        """
        Add a Supporter to the list of supporters of the application.
        """
        if user == self.submitter:
            raise NameError('Supporter can not be the submitter of a ' \
                            'application.')
        if self.permitted is not None:
            raise NameError('This application is already permitted.')
        if user not in self.supporter.all():
            self.supporter.add(user)
        self.writelog(_("Supporter: +%s") % (user))

    def unsupport(self, user):
        """
        remove a supporter from the list of supporters of the application
        """
        if self.permitted is not None:
            raise NameError('This application is already permitted.')
        if user in self.supporter.all():
            self.supporter.remove(user)
        self.writelog(_("Supporter: -%s") % (user))

    def set_number(self, number=None, user=None):
        """
        Set a number for ths application.
        """
        if self.number is not None:
            raise NameError('This application has already a number.')
        if number is None:
            try:
                number = Application.objects.aggregate(Max('number')) \
                            ['number__max'] + 1
            except TypeError:
                number = 1
        self.number = number
        self.save()
        self.writelog(_("Number set: %s") % (self.number), user)
        return self.number

    def permit(self, user=None):
        """
        Change the status of this application to permit.
        """
        self.set_status(user, "per")
        aversion = self.last_version
        if self.number is None:
            self.set_number()
        self.permitted = aversion
        self.save()
        self.writelog(_("Version %s permitted") % (aversion.aid), user)
        return self.permitted

    def notpermit(self, user=None):
        """
        Change the status of this application to 'not permitted (rejected)'.
        """
        self.set_status(user, "nop")
        #TODO: reject last version
        aversion = self.last_version
        #self.permitted = aversion
        if self.number is None:
            self.set_number()
        self.save()
        self.writelog(_("Version %s not permitted") % (self.last_version.aid), user)

    def set_status(self, user, status, force=False):
        """
        Set the status of the application.
        """
        error = True
        for a, b in Application.STATUS:
            if status == a:
                error = False
                break
        if error:
            raise NameError('%s is not a valid status.' % status)
        if self.status == status:
            raise NameError('The application status is already %s.' \
                            % self.status)

        actions = []
        actions = self.get_allowed_actions(user)
        if status not in actions and not force:
            raise NameError('The application status is: %s. You can not set' \
                            ' the status to %s.' % (self.status, status))

        oldstatus = self.get_status_display()
        self.status = status
        self.save()
        self.writelog(_("Status modified")+": %s -> %s" \
                      % (oldstatus, self.get_status_display()), user)

    def get_allowed_actions(self, user=None):
        """
        Return a list of all the allowed status.
        """
        actions = []

        # check if user allowed to withdraw an application
        if   (self.status == "pub"
          and self.number \
          and user == self.submitter) \
        or   (self.status == "pub" \
          and self.number \
          and user.has_perm("application.can_manage_application")) \
        or   (self.status == "per" \
          and user == self.submitter) \
        or (self.status == "per" \
          and user.has_perm("application.can_manage_application")):
            actions.append("wit")

        # Check if the user can support and unspoort the application
        if  self.status == "pub" \
        and user != self.submitter \
        and user not in self.supporter.all():
            actions.append("support")

        if self.status == "pub" and user in self.supporter.all():
            actions.append("unsupport")

        #Check if the user can edit the application
        if user == self.submitter \
        or user.has_perm("application.can_manage_application"):
            actions.append("edit")

        #Check if the user can delete the application
        if  self.number is None \
        and self.status == "pub" \
        and (self.submitter == user \
          or user.has_perm("application.can_manage_application")):
            actions.append("delete")

        #For the rest, all actions need the manage permission
        if not user.has_perm("application.can_manage_application"):
            return actions

        if self.status == "pub":
            actions.append("nop")
            actions.append("per")
            if self.number == None:
                actions.append("setnumber")

        if self.status == "per":
            actions.append("acc")
            actions.append("rej")
            actions.append("adj")
            actions.append("noc")
            actions.append("com")
            actions.append("genpoll")
            if self.unpermitted_changes:
                actions.append("permitversion")
                actions.append("rejectversion")

        if self.number and not self.itemapplication_set.all():
            actions.append("createitem")

        return actions

    def delete(self, force=False):
        """
        Delete the application. It is not possible, if the application has
        allready a number
        """
        if self.number and not force:
            raise NameError('The application has already a number. ' \
                            'You can not delete it.')
        super(Application, self).delete()

    def writelog(self, text, user=None):
        if not self.log:
            self.log = ""
        self.log += u"%s | %s" % (datetime.now().strftime("%d.%m.%Y %H:%M:%S"), text)
        if user is not None:
            self.log += u" (by %s)" % (user.username)
        self.log += "\n"
        self.save()

    def __getattr__(self, name):
        """
        if name is title, text, reason or time,
            Return this attribute from the newest version of the application
        """
        if name in ('title', 'text', 'reason', 'time'):
            try:
                return self.last_version.__dict__[name]
            except TypeError:
                raise AttributeError(name)
            except AttributeError:
                raise AttributeError(name)
        raise AttributeError(name)

    def gen_poll(self, user=None):
        """
        Generates a poll object for the application
        """
        from poll.models import Poll
        poll = Poll(optiondecision=True, \
                    application=self)
        poll.save()
        poll.add_option(self)
        self.writelog(_("Poll created"), user)
        return poll

    @models.permalink
    def get_absolute_url(self, link='view'):
        if link == 'view':
            return ('application_view', [str(self.id)])
        if link == 'delete':
            return ('application_delete', [str(self.id)])

    def __unicode__(self):
        try:
            return self.last_version.title
        except AttributeError:
            return "no title jet"

    class Meta:
        permissions = (
            ('can_view_application', _("Can see applications")),
            ('can_insert_application', _("Can insert new applications")),
            ('can_support_application', _("Can support applications")),
            ('can_manage_application', _("Can manage applications")),
        )


class AVersion(models.Model):
    title = models.CharField(max_length=100)
    text = models.TextField()
    reason = models.TextField(null=True, blank=True)
    rejected = models.BooleanField()
    time = models.DateTimeField(auto_now=True)
    application = models.ForeignKey(Application)

    def __unicode__(self):
        return "%s %s" % (self.id, self.title)

    @property
    def aid(self):
        try:
            return self._aid
        except AttributeError:
            self._aid = AVersion.objects \
                .filter(application=self.application) \
                .filter(id__lte=self.id).count()
            return self._aid
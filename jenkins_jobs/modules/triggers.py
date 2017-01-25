# Copyright 2012 Hewlett-Packard Development Company, L.P.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


"""
Triggers define what causes a Jenkins job to start building.

**Component**: triggers
  :Macro: trigger
  :Entry Point: jenkins_jobs.triggers

Example::

  job:
    name: test_job

    triggers:
      - timed: '@daily'
"""

import logging
import pkg_resources
import re
import xml.etree.ElementTree as XML

import six

from jenkins_jobs.errors import InvalidAttributeError
from jenkins_jobs.errors import JenkinsJobsException
from jenkins_jobs.errors import MissingAttributeError
import jenkins_jobs.modules.base
from jenkins_jobs.modules import hudson_model
from jenkins_jobs.modules.helpers import convert_mapping_to_xml

logger = logging.getLogger(str(__name__))


def gerrit_handle_legacy_configuration(data):
    hyphenizer = re.compile("[A-Z]")

    def hyphenize(attr):
        """Convert strings like triggerOn to trigger-on.
        """
        return hyphenizer.sub(lambda x: "-%s" % x.group(0).lower(),
                              attr)

    def convert_dict(d, old_keys):
        for old_key in old_keys:
            if old_key in d:
                new_key = hyphenize(old_key)
                logger.warning(
                    "'%s' is deprecated and will be removed after "
                    "1.0.0, please use '%s' instead", old_key, new_key)
                d[new_key] = d[old_key]
                del d[old_key]

    convert_dict(data, [
        'triggerOnPatchsetUploadedEvent',
        'triggerOnChangeAbandonedEvent',
        'triggerOnChangeMergedEvent',
        'triggerOnChangeRestoredEvent',
        'triggerOnCommentAddedEvent',
        'triggerOnDraftPublishedEvent',
        'triggerOnRefUpdatedEvent',
        'triggerApprovalCategory',
        'triggerApprovalValue',
        'overrideVotes',
        'gerritBuildSuccessfulVerifiedValue',
        'gerritBuildFailedVerifiedValue',
        'failureMessage',
        'skipVote',
    ])

    for project in data.get('projects', []):
        convert_dict(project, [
            'projectCompareType',
            'projectPattern',
            'branchCompareType',
            'branchPattern',
        ])

    mapping_obj_type = type(data)

    old_format_events = mapping_obj_type(
        (key, should_register) for key, should_register in six.iteritems(data)
        if key.startswith('trigger-on-'))
    trigger_on = data.setdefault('trigger-on', [])
    if old_format_events:
        logger.warning(
            "The events: %s; which you used is/are deprecated. "
            "Please use 'trigger-on' instead.",
            ', '.join(old_format_events))

    if old_format_events and trigger_on:
        raise JenkinsJobsException(
            'Both, the new format (trigger-on) and old format (trigger-on-*) '
            'gerrit events format found. Please use either the new or the old '
            'format of trigger events definition.')

    trigger_on.extend(event_name[len('trigger-on-'):]
                      for event_name, should_register
                      in six.iteritems(old_format_events) if should_register)

    for idx, event in enumerate(trigger_on):
        if event == 'comment-added-event':
            trigger_on[idx] = events = mapping_obj_type()
            try:
                events['comment-added-event'] = mapping_obj_type((
                    ('approval-category', data['trigger-approval-category']),
                    ('approval-value', data['trigger-approval-value'])
                ))
            except KeyError:
                raise JenkinsJobsException(
                    'The comment-added-event trigger requires which approval '
                    'category and value you want to trigger the job. '
                    'It should be specified by the approval-category '
                    'and approval-value properties.')


def build_gerrit_triggers(xml_parent, data):
    available_simple_triggers = {
        'change-abandoned-event': 'PluginChangeAbandonedEvent',
        'change-merged-event': 'PluginChangeMergedEvent',
        'change-restored-event': 'PluginChangeRestoredEvent',
        'draft-published-event': 'PluginDraftPublishedEvent',
        'patchset-uploaded-event': 'PluginPatchsetCreatedEvent',
        'patchset-created-event': 'PluginPatchsetCreatedEvent',
        'ref-updated-event': 'PluginRefUpdatedEvent',
    }
    tag_namespace = 'com.sonyericsson.hudson.plugins.gerrit.trigger.'   \
        'hudsontrigger.events'

    trigger_on_events = XML.SubElement(xml_parent, 'triggerOnEvents')

    for event in data.get('trigger-on', []):
        if isinstance(event, six.string_types):
            tag_name = available_simple_triggers.get(event)
            if event == 'patchset-uploaded-event':
                logger.warning(
                    "'%s' is deprecated. Use 'patchset-created-event' "
                    "format instead.", event)

            if not tag_name:
                known = ', '.join(available_simple_triggers.keys()
                                  + ['comment-added-event',
                                     'comment-added-contains-event'])
                msg = ("The event '%s' under 'trigger-on' is not one of the "
                       "known: %s.") % (event, known)
                raise JenkinsJobsException(msg)
            XML.SubElement(trigger_on_events,
                           '%s.%s' % (tag_namespace, tag_name))
        else:
            if 'patchset-created-event' in event.keys():
                pce = event['patchset-created-event']
                pc = XML.SubElement(
                    trigger_on_events,
                    '%s.%s' % (tag_namespace, 'PluginPatchsetCreatedEvent'))
                XML.SubElement(pc, 'excludeDrafts').text = str(
                    pce.get('exclude-drafts', False)).lower()
                XML.SubElement(pc, 'excludeTrivialRebase').text = str(
                    pce.get('exclude-trivial-rebase', False)).lower()
                XML.SubElement(pc, 'excludeNoCodeChange').text = str(
                    pce.get('exclude-no-code-change', False)).lower()

            if 'comment-added-event' in event.keys():
                comment_added_event = event['comment-added-event']
                cadded = XML.SubElement(
                    trigger_on_events,
                    '%s.%s' % (tag_namespace, 'PluginCommentAddedEvent'))
                XML.SubElement(cadded, 'verdictCategory').text = \
                    comment_added_event['approval-category']
                XML.SubElement(
                    cadded,
                    'commentAddedTriggerApprovalValue').text = \
                    str(comment_added_event['approval-value'])

            if 'comment-added-contains-event' in event.keys():
                comment_added_event = event['comment-added-contains-event']
                caddedc = XML.SubElement(
                    trigger_on_events,
                    '%s.%s' % (tag_namespace,
                               'PluginCommentAddedContainsEvent'))
                XML.SubElement(caddedc, 'commentAddedCommentContains').text = \
                    comment_added_event['comment-contains-value']


def build_gerrit_skip_votes(xml_parent, data):
    outcomes = [('successful', 'onSuccessful'),
                ('failed', 'onFailed'),
                ('unstable', 'onUnstable'),
                ('notbuilt', 'onNotBuilt')]

    skip_vote_node = XML.SubElement(xml_parent, 'skipVote')
    skip_vote = data.get('skip-vote', {})
    for result_kind, tag_name in outcomes:
        if skip_vote.get(result_kind, False):
            XML.SubElement(skip_vote_node, tag_name).text = 'true'
        else:
            XML.SubElement(skip_vote_node, tag_name).text = 'false'


def gerrit(registry, xml_parent, data):
    """yaml: gerrit

    Trigger on a Gerrit event.
    Requires the Jenkins :jenkins-wiki:`Gerrit Trigger Plugin <Gerrit+Trigger>`
    version >= 2.6.0.

    :arg list trigger-on: Events to react on. Please use either the new
      **trigger-on**, or the old **trigger-on-*** events definitions. You
      cannot use both at once.

      .. _trigger_on:

      :Trigger on:

         * **patchset-created-event** (`dict`) -- Trigger upon patchset
           creation.

           :Patchset created:
               * **exclude-drafts** (`bool`) -- exclude drafts (default false)
               * **exclude-trivial-rebase** (`bool`) -- exclude trivial rebase
                 (default false)
               * **exclude-no-code-change** (`bool`) -- exclude no code change
                 (default false)

           Exclude drafts|trivial-rebase|no-code-change needs
           Gerrit Trigger v2.12.0

         * **patchset-uploaded-event** -- Trigger upon patchset creation
           (this is a alias for `patchset-created-event`).

           .. deprecated:: 1.1.0  Please use :ref:`trigger-on <trigger_on>`.

         * **change-abandoned-event** -- Trigger on patchset abandoned.
           Requires Gerrit Trigger Plugin version >= 2.8.0.
         * **change-merged-event** -- Trigger on change merged
         * **change-restored-event** -- Trigger on change restored. Requires
           Gerrit Trigger Plugin version >= 2.8.0
         * **draft-published-event** -- Trigger on draft published event.
         * **ref-updated-event** -- Trigger on ref-updated.
         * **comment-added-event** (`dict`) -- Trigger on comment added.

           :Comment added:
               * **approval-category** (`str`) -- Approval (verdict) category
                 (for example 'APRV', 'CRVW', 'VRIF' -- see `Gerrit access
                 control
                 <http://gerrit.googlecode.com/svn/documentation/2.1/
                 access-control.html#categories>`_

               * **approval-value** -- Approval value for the comment added.
         * **comment-added-contains-event** (`dict`) -- Trigger on comment
           added contains Regular Expression.

           :Comment added contains:
               * **comment-contains-value** (`str`) -- Comment contains
                 Regular Expression value.

    :arg bool trigger-on-patchset-uploaded-event: Trigger on patchset upload.

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg bool trigger-on-change-abandoned-event: Trigger on change abandoned.
        Requires Gerrit Trigger Plugin version >= 2.8.0

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg bool trigger-on-change-merged-event: Trigger on change merged

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg bool trigger-on-change-restored-event: Trigger on change restored.
        Requires Gerrit Trigger Plugin version >= 2.8.0

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg bool trigger-on-comment-added-event: Trigger on comment added

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg bool trigger-on-draft-published-event: Trigger on draft published
        event

        .. deprecated:: 1.1.0  Please use :ref:`trigger-on <trigger_on>`.

    :arg bool trigger-on-ref-updated-event: Trigger on ref-updated

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg str trigger-approval-category: Approval category for comment added

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg int trigger-approval-value: Approval value for comment added

        .. deprecated:: 1.1.0. Please use :ref:`trigger-on <trigger_on>`.

    :arg bool override-votes: Override default vote values
    :arg int gerrit-build-started-verified-value: Started ''Verified'' value
    :arg int gerrit-build-successful-verified-value: Successful ''Verified''
        value
    :arg int gerrit-build-failed-verified-value: Failed ''Verified'' value
    :arg int gerrit-build-unstable-verified-value: Unstable ''Verified'' value
    :arg int gerrit-build-notbuilt-verified-value: Not built ''Verified''
        value
    :arg int gerrit-build-started-codereview-value: Started ''CodeReview''
        value
    :arg int gerrit-build-successful-codereview-value: Successful
        ''CodeReview'' value
    :arg int gerrit-build-failed-codereview-value: Failed ''CodeReview'' value
    :arg int gerrit-build-unstable-codereview-value: Unstable ''CodeReview''
        value
    :arg int gerrit-build-notbuilt-codereview-value: Not built ''CodeReview''
        value
    :arg str failure-message: Message to leave on failure (default '')
    :arg str successful-message: Message to leave on success (default '')
    :arg str unstable-message: Message to leave when unstable (default '')
    :arg str notbuilt-message: Message to leave when not built (default '')
    :arg str failure-message-file: Sets the filename within the workspace from
        which to retrieve the unsuccessful review message. (optional)
    :arg list projects: list of projects to match

      :Project: * **project-compare-type** (`str`) --  ''PLAIN'', ''ANT'' or
                  ''REG_EXP''
                * **project-pattern** (`str`) -- Project name pattern to match
                * **branch-compare-type** (`str`) -- ''PLAIN'', ''ANT'' or
                  ''REG_EXP'' (not used if `branches` list is specified)

                  .. deprecated:: 1.1.0  Please use :ref:`branches <branches>`.

                * **branch-pattern** (`str`) -- Branch name pattern to match
                  (not used if `branches` list is specified)

                  .. deprecated:: 1.1.0  Please use :ref:`branches <branches>`.

                .. _branches:

                * **branches** (`list`) -- List of branches to match
                  (optional)

                  :Branch: * **branch-compare-type** (`str`) -- ''PLAIN'',
                             ''ANT'' or ''REG_EXP'' (optional) (default
                             ''PLAIN'')
                           * **branch-pattern** (`str`) -- Branch name pattern
                             to match

                * **file-paths** (`list`) -- List of file paths to match
                  (optional)

                  :File Path: * **compare-type** (`str`) -- ''PLAIN'', ''ANT''
                                or ''REG_EXP'' (optional) (default ''PLAIN'')
                              * **pattern** (`str`) -- File path pattern to
                                match

                * **forbidden-file-paths** (`list`) -- List of file paths to
                  skip triggering (optional)

                  :Forbidden File Path: * **compare-type** (`str`) --
                                ''PLAIN'', ''ANT'' or ''REG_EXP'' (optional)
                                (default ''PLAIN'')
                              * **pattern** (`str`) -- File path pattern to
                                match

                * **topics** (`list`) -- List of topics to match
                  (optional)

                  :Topic: * **compare-type** (`str`) -- ''PLAIN'', ''ANT'' or
                            ''REG_EXP'' (optional) (default ''PLAIN'')
                          * **pattern** (`str`) -- Topic name pattern to
                            match

                * **disable-strict-forbidden-file-verification** (`bool`) --
                      Enabling this option will allow an event to trigger a
                      build if the event contains BOTH one or more wanted file
                      paths AND one or more forbidden file paths.  In other
                      words, with this option, the build will not get
                      triggered if the change contains only forbidden files,
                      otherwise it will get triggered. Requires plugin
                      version >= 2.16.0 (default false)

    :arg dict skip-vote: map of build outcomes for which Jenkins must skip
        vote. Requires Gerrit Trigger Plugin version >= 2.7.0

        :Outcome: * **successful** (`bool`)
                  * **failed** (`bool`)
                  * **unstable** (`bool`)
                  * **notbuilt** (`bool`)

    :arg bool silent:  When silent mode is on there will be no communication
        back to Gerrit, i.e. no build started/failed/successful approve
        messages etc. If other non-silent jobs are triggered by the same
        Gerrit event as this job, the result of this job's build will not be
        counted in the end result of the other jobs. (default false)
    :arg bool silent-start: Sets silent start mode to on or off. When silent
        start mode is on there will be no 'build started' messages sent back
        to Gerrit. (default false)
    :arg bool escape-quotes: escape quotes in the values of Gerrit change
        parameters (default true)
    :arg bool no-name-and-email: Do not pass compound 'name and email'
        parameters (default false)
    :arg bool readable-message: If parameters regarding multiline text,
        e.g. commit message, should be as human readable or not. If false,
        those parameters are Base64 encoded to keep environment variables
        clean. (default false)
    :arg str dependency-jobs: All jobs on which this job depends. If a commit
        should trigger both a dependency and this job, the dependency will be
        built first. Use commas to separate job names. Beware of cyclic
        dependencies. (optional)
    :arg str notification-level: Defines to whom email notifications should be
        sent. This can either be nobody ('NONE'), the change owner ('OWNER'),
        reviewers and change owner ('OWNER_REVIEWERS'), all interested users
        i.e. owning, reviewing, watching, and starring ('ALL') or server
        default ('SERVER_DEFAULT'). (default 'SERVER_DEFAULT')
    :arg bool dynamic-trigger-enabled: Enable/disable the dynamic trigger
        (default false)
    :arg str dynamic-trigger-url: if you specify this option, the Gerrit
        trigger configuration will be fetched from there on a regular interval
    :arg bool trigger-for-unreviewed-patches: trigger patchset-created events
        for changes that were uploaded while connection to Gerrit was down
        (default false). Requires Gerrit Trigger Plugin version >= 2.11.0
    :arg str custom-url: Custom URL for a message sent to Gerrit. Build
        details URL will be used if empty. (default '')
    :arg str server-name: Name of the server to trigger on, or ''__ANY__'' to
        trigger on any configured Gerrit server (default '__ANY__'). Requires
        Gerrit Trigger Plugin version >= 2.11.0

    You may select one or more Gerrit events upon which to trigger.
    You must also supply at least one project and branch, optionally
    more.  If you select the comment-added trigger, you should also
    indicate which approval category and value you want to trigger the
    job.

    Until version 0.4.0 of Jenkins Job Builder, camelCase keys were used to
    configure Gerrit Trigger Plugin, instead of hyphenated-keys.  While still
    supported, camedCase keys are deprecated and should not be used. Support
    for this will be removed after 1.0.0 is released.

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/gerrit004.yaml
       :language: yaml

    """

    def get_compare_type(xml_tag, compare_type):
        valid_compare_types = ['PLAIN',
                               'ANT',
                               'REG_EXP']

        if compare_type not in valid_compare_types:
            raise InvalidAttributeError(xml_tag, compare_type,
                                        valid_compare_types)
        return compare_type

    gerrit_handle_legacy_configuration(data)

    projects = data.get('projects', [])
    gtrig = XML.SubElement(xml_parent,
                           'com.sonyericsson.hudson.plugins.gerrit.trigger.'
                           'hudsontrigger.GerritTrigger')
    XML.SubElement(gtrig, 'spec')
    gprojects = XML.SubElement(gtrig, 'gerritProjects')
    for project in projects:
        gproj = XML.SubElement(gprojects,
                               'com.sonyericsson.hudson.plugins.gerrit.'
                               'trigger.hudsontrigger.data.GerritProject')
        XML.SubElement(gproj, 'compareType').text = get_compare_type(
            'project-compare-type', project.get(
                'project-compare-type', 'PLAIN'))
        XML.SubElement(gproj, 'pattern').text = project['project-pattern']

        branches = XML.SubElement(gproj, 'branches')
        project_branches = project.get('branches', [])

        if 'branch-compare-type' in project and 'branch-pattern' in project:
            warning = 'branch-compare-type and branch-pattern at project ' \
                      'level are deprecated and support will be removed ' \
                      'in a later version of Jenkins Job Builder; '
            if project_branches:
                warning += 'discarding values and using values from ' \
                           'branches section'
            else:
                warning += 'please use branches section instead'
            logger.warning(warning)
        if not project_branches:
            project_branches = [
                {'branch-compare-type': project.get(
                    'branch-compare-type', 'PLAIN'),
                 'branch-pattern': project['branch-pattern']}]
        for branch in project_branches:
            gbranch = XML.SubElement(
                branches, 'com.sonyericsson.hudson.plugins.'
                'gerrit.trigger.hudsontrigger.data.Branch')
            XML.SubElement(gbranch, 'compareType').text = get_compare_type(
                'branch-compare-type', branch.get(
                    'branch-compare-type', 'PLAIN'))
            XML.SubElement(gbranch, 'pattern').text = branch['branch-pattern']

        project_file_paths = project.get('file-paths', [])
        if project_file_paths:
            fps_tag = XML.SubElement(gproj, 'filePaths')
            for file_path in project_file_paths:
                fp_tag = XML.SubElement(fps_tag,
                                        'com.sonyericsson.hudson.plugins.'
                                        'gerrit.trigger.hudsontrigger.data.'
                                        'FilePath')
                XML.SubElement(fp_tag, 'compareType').text = get_compare_type(
                    'compare-type', file_path.get('compare-type', 'PLAIN'))
                XML.SubElement(fp_tag, 'pattern').text = file_path['pattern']

        project_forbidden_file_paths = project.get('forbidden-file-paths', [])
        if project_forbidden_file_paths:
            ffps_tag = XML.SubElement(gproj, 'forbiddenFilePaths')
            for forbidden_file_path in project_forbidden_file_paths:
                ffp_tag = XML.SubElement(ffps_tag,
                                         'com.sonyericsson.hudson.plugins.'
                                         'gerrit.trigger.hudsontrigger.data.'
                                         'FilePath')
                XML.SubElement(ffp_tag, 'compareType').text = get_compare_type(
                    'compare-type', forbidden_file_path.get('compare-type',
                                                            'PLAIN'))
                XML.SubElement(ffp_tag, 'pattern').text = \
                    forbidden_file_path['pattern']

        topics = project.get('topics', [])
        if topics:
            topics_tag = XML.SubElement(gproj, 'topics')
            for topic in topics:
                topic_tag = XML.SubElement(topics_tag,
                                           'com.sonyericsson.hudson.plugins.'
                                           'gerrit.trigger.hudsontrigger.data.'
                                           'Topic')
                XML.SubElement(topic_tag, 'compareType').text = \
                    get_compare_type('compare-type', topic.get('compare-type',
                                                               'PLAIN'))
                XML.SubElement(topic_tag, 'pattern').text = topic['pattern']

        XML.SubElement(gproj,
                       'disableStrictForbiddenFileVerification').text = str(
            project.get('disable-strict-forbidden-file-verification',
                        False)).lower()

    build_gerrit_skip_votes(gtrig, data)
    general_mappings = [
        ('silent', 'silentMode', False),
        ('silent-start', 'silentStartMode', False),
        ('escape-quotes', 'escapeQuotes', True),
        ('no-name-and-email', 'noNameAndEmailParameters', False),
        ('readable-message', 'readableMessage', False),
        ('dependency-jobs', 'dependencyJobsNames', ''),
    ]
    convert_mapping_to_xml(gtrig, data, general_mappings, fail_required=True)
    notification_levels = ['NONE', 'OWNER', 'OWNER_REVIEWERS', 'ALL',
                           'SERVER_DEFAULT']
    notification_level = data.get('notification-level', 'SERVER_DEFAULT')
    if notification_level not in notification_levels:
        raise InvalidAttributeError('notification-level', notification_level,
                                    notification_levels)
    if notification_level == 'SERVER_DEFAULT':
        XML.SubElement(gtrig, 'notificationLevel').text = ''
    else:
        XML.SubElement(gtrig, 'notificationLevel').text = notification_level
    XML.SubElement(gtrig, 'dynamicTriggerConfiguration').text = str(
        data.get('dynamic-trigger-enabled', False))
    XML.SubElement(gtrig, 'triggerConfigURL').text = str(
        data.get('dynamic-trigger-url', ''))
    XML.SubElement(gtrig, 'allowTriggeringUnreviewedPatches').text = str(
        data.get('trigger-for-unreviewed-patches', False)).lower()
    build_gerrit_triggers(gtrig, data)
    override = str(data.get('override-votes', False)).lower()
    if override == 'true':
        for yamlkey, xmlkey in [('gerrit-build-started-verified-value',
                                 'gerritBuildStartedVerifiedValue'),
                                ('gerrit-build-successful-verified-value',
                                 'gerritBuildSuccessfulVerifiedValue'),
                                ('gerrit-build-failed-verified-value',
                                 'gerritBuildFailedVerifiedValue'),
                                ('gerrit-build-unstable-verified-value',
                                 'gerritBuildUnstableVerifiedValue'),
                                ('gerrit-build-notbuilt-verified-value',
                                 'gerritBuildNotBuiltVerifiedValue'),
                                ('gerrit-build-started-codereview-value',
                                 'gerritBuildStartedCodeReviewValue'),
                                ('gerrit-build-successful-codereview-value',
                                 'gerritBuildSuccessfulCodeReviewValue'),
                                ('gerrit-build-failed-codereview-value',
                                 'gerritBuildFailedCodeReviewValue'),
                                ('gerrit-build-unstable-codereview-value',
                                 'gerritBuildUnstableCodeReviewValue'),
                                ('gerrit-build-notbuilt-codereview-value',
                                 'gerritBuildNotBuiltCodeReviewValue')]:
            if data.get(yamlkey) is not None:
                # str(int(x)) makes input values like '+1' work
                XML.SubElement(gtrig, xmlkey).text = str(
                    int(data.get(yamlkey)))
    message_mappings = [
        ('start-message', 'buildStartMessage', ''),
        ('failure-message', 'buildFailureMessage', ''),
        ('successful-message', 'buildSuccessfulMessage', ''),
        ('unstable-message', 'buildUnstableMessage', ''),
        ('notbuilt-message', 'buildNotBuiltMessage', ''),
        ('failure-message-file', 'buildUnsuccessfulFilepath', ''),
        ('custom-url', 'customUrl', ''),
        ('server-name', 'serverName', '__ANY__'),
    ]
    convert_mapping_to_xml(gtrig, data, message_mappings, fail_required=True)


def pollscm(registry, xml_parent, data):
    """yaml: pollscm
    Poll the SCM to determine if there has been a change.

    :Parameter: the polling interval (cron syntax)

    .. deprecated:: 1.3.0. Please use :ref:`cron <cron>`.

    .. _cron:

    :arg string cron: the polling interval (cron syntax, required)
    :arg bool ignore-post-commit-hooks: Ignore changes notified by SCM
        post-commit hooks. The subversion-plugin supports this since
        version 1.44. (default false)

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/pollscm002.yaml
       :language: yaml
    """

    try:
        cron = data['cron']
        ipch = str(data.get('ignore-post-commit-hooks', False)).lower()
    except KeyError as e:
        # ensure specific error on the attribute not being set is raised
        # for new format
        raise MissingAttributeError(e)
    except TypeError:
        # To keep backward compatibility
        logger.warning(
            "Your pollscm usage is deprecated, please use"
            " the syntax described in the documentation"
            " instead")
        cron = data
        ipch = 'false'

    if not cron and cron != '':
        raise InvalidAttributeError('cron', cron)

    scmtrig = XML.SubElement(xml_parent, 'hudson.triggers.SCMTrigger')
    XML.SubElement(scmtrig, 'spec').text = cron
    XML.SubElement(scmtrig, 'ignorePostCommitHooks').text = ipch


def build_content_type(xml_parent, entries, namespace, collection_suffix,
                       entry_suffix, prefix, collection_name, element_name):
    content_type = XML.SubElement(
        xml_parent, '{0}.{1}{2}'.format(namespace, prefix, collection_suffix))
    if entries:
        collection = XML.SubElement(content_type, collection_name)
        for entry in entries:
            content_entry = XML.SubElement(
                collection, '{0}.{1}{2}'.format(namespace, prefix,
                                                entry_suffix))
            XML.SubElement(content_entry, element_name).text = entry


def pollurl(registry, xml_parent, data):
    """yaml: pollurl
    Trigger when the HTTP response from a URL changes.
    Requires the Jenkins :jenkins-wiki:`URLTrigger Plugin <URLTrigger+Plugin>`.

    :arg string cron: cron syntax of when to run (default '')
    :arg string polling-node: Restrict where the polling should run.
                              (optional)
    :arg list urls: List of URLs to monitor

      :URL: * **url** (`str`) -- URL to monitor for changes (required)
            * **proxy** (`bool`) -- Activate the Jenkins proxy (default false)
            * **timeout** (`int`) -- Connect/read timeout in seconds
              (default 300)
            * **username** (`string`) -- User name for basic authentication
              (optional)
            * **password** (`string`) -- Password for basic authentication
              (optional)
            * **check-status** (`int`) -- Check for a specific HTTP status
              code (optional)
            * **check-etag** (`bool`) -- Check the HTTP ETag for changes
              (default false)
            * **check-date** (`bool`) -- Check the last modification date of
              the URL (default false)
            * **check-content** (`list`) -- List of content type changes to
              monitor

              :Content Type: * **simple** (`bool`) -- Trigger on any change to
                               the content of the URL (default false)
                             * **json** (`list`) -- Trigger on any change to
                               the listed JSON paths
                             * **text** (`list`) -- Trigger on any change to
                               the listed regular expressions
                             * **xml** (`list`) -- Trigger on any change to
                               the listed XPath expressions

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/pollurl001.yaml
    """

    namespace = 'org.jenkinsci.plugins.urltrigger.'
    valid_content_types = {
        'simple': ['Simple', '', '', []],
        'json': ['JSON', 'jsonPaths', 'jsonPath', None],
        'text': ['TEXT', 'regExElements', 'regEx', None],
        'xml': ['XML', 'xPaths', 'xPath', None]
    }
    urltrig = XML.SubElement(xml_parent,
                             namespace + 'URLTrigger')
    node = data.get('polling-node')
    XML.SubElement(urltrig, 'spec').text = data.get('cron', '')
    XML.SubElement(urltrig, 'labelRestriction').text = str(bool(node)).lower()
    if node:
        XML.SubElement(urltrig, 'triggerLabel').text = node
    entries = XML.SubElement(urltrig, 'entries')
    urls = data.get('urls', [])
    if not urls:
        raise JenkinsJobsException('At least one url must be provided')
    for url in urls:
        entry = XML.SubElement(entries, namespace + 'URLTriggerEntry')
        XML.SubElement(entry, 'url').text = url['url']
        XML.SubElement(entry, 'proxyActivated').text = \
            str(url.get('proxy', False)).lower()
        if 'username' in url:
            XML.SubElement(entry, 'username').text = url['username']
        if 'password' in url:
            XML.SubElement(entry, 'password').text = url['password']
        if 'check-status' in url:
            XML.SubElement(entry, 'checkStatus').text = 'true'
            XML.SubElement(entry, 'statusCode').text = \
                str(url.get('check-status'))
        else:
            XML.SubElement(entry, 'checkStatus').text = 'false'
            XML.SubElement(entry, 'statusCode').text = '200'
        XML.SubElement(entry, 'timeout').text = \
            str(url.get('timeout', 300))
        XML.SubElement(entry, 'checkETag').text = \
            str(url.get('check-etag', False)).lower()
        XML.SubElement(entry, 'checkLastModificationDate').text = \
            str(url.get('check-date', False)).lower()
        check_content = url.get('check-content', [])
        XML.SubElement(entry, 'inspectingContent').text = \
            str(bool(check_content)).lower()
        content_types = XML.SubElement(entry, 'contentTypes')
        for entry in check_content:
            type_name = next(iter(entry.keys()))
            if type_name not in valid_content_types:
                raise JenkinsJobsException('check-content must be one of : %s'
                                           % ', '.join(valid_content_types.
                                                       keys()))

            content_type = valid_content_types.get(type_name)
            if entry[type_name]:
                sub_entries = content_type[3]
                if sub_entries is None:
                    sub_entries = entry[type_name]
                build_content_type(content_types, sub_entries,
                                   namespace + 'content', 'ContentType',
                                   'ContentEntry', *content_type[0:3])


def timed(registry, xml_parent, data):
    """yaml: timed
    Trigger builds at certain times.

    :Parameter: when to run the job (cron syntax)

    Example::

      triggers:
        - timed: "@midnight"
    """
    scmtrig = XML.SubElement(xml_parent, 'hudson.triggers.TimerTrigger')
    XML.SubElement(scmtrig, 'spec').text = data


def bitbucket(registry, xml_parent, data):
    """yaml: bitbucket
    Trigger a job when bitbucket repository is pushed to.
    Requires the Jenkins :jenkins-wiki:`BitBucket Plugin
    <BitBucket+Plugin>`.

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/bitbucket.yaml
    """
    bbtrig = XML.SubElement(xml_parent, 'com.cloudbees.jenkins.'
                            'plugins.BitBucketTrigger')
    XML.SubElement(bbtrig, 'spec').text = ''


def github(registry, xml_parent, data):
    """yaml: github
    Trigger a job when github repository is pushed to.
    Requires the Jenkins :jenkins-wiki:`GitHub Plugin <GitHub+Plugin>`.

    Example::

      triggers:
        - github
    """
    ghtrig = XML.SubElement(xml_parent, 'com.cloudbees.jenkins.'
                            'GitHubPushTrigger')
    XML.SubElement(ghtrig, 'spec').text = ''


def github_pull_request(registry, xml_parent, data):
    """yaml: github-pull-request
    Build pull requests in github and report results.
    Requires the Jenkins :jenkins-wiki:`GitHub Pull Request Builder Plugin
    <GitHub+pull+request+builder+plugin>`.

    :arg list admin-list: the users with admin rights (optional)
    :arg list white-list: users whose pull requests build (optional)
    :arg list org-list: orgs whose users should be white listed (optional)
    :arg bool allow-whitelist-orgs-as-admins: members of white listed orgs
        will have admin rights. (default false)
    :arg string cron: cron syntax of when to run (optional)
    :arg string trigger-phrase: when filled, commenting this phrase
        in the pull request will trigger a build (optional)
    :arg bool only-trigger-phrase: only commenting the trigger phrase
        in the pull request will trigger a build (default false)
    :arg bool github-hooks: use github hook (default false)
    :arg bool permit-all: build every pull request automatically
        without asking (default false)
    :arg bool auto-close-on-fail: close failed pull request automatically
        (default false)
    :arg list white-list-target-branches: Adding branches to this whitelist
        allows you to selectively test pull requests destined for these
        branches only. Supports regular expressions (e.g. 'master',
        'feature-.*'). (optional)
    :arg string auth-id: the auth id to use (optional)
    :arg string build-desc-template: the template for build descriptions in
        jenkins (optional)
    :arg string status-context: the context to include on PR status comments
        (optional)
    :arg string triggered-status: the status message to set when the build has
        been triggered (optional)
    :arg string started-status: the status comment to set when the build has
        been started (optional)
    :arg string status-url: the status URL to set (optional)
    :arg bool status-add-test-results: add test result one-liner to status
        message (optional)
    :arg string success-status: the status message to set if the job succeeds
        (optional)
    :arg string failure-status: the status message to set if the job fails
        (optional)
    :arg string error-status: the status message to set if the job errors
        (optional)
    :arg string success-comment: comment to add to the PR on a successful job
        (optional)
    :arg string failure-comment: comment to add to the PR on a failed job
        (optional)
    :arg string error-comment: comment to add to the PR on an errored job
        (optional)
    :arg bool cancel-builds-on-update: cancel existing builds when a PR is
        updated (optional)

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/github-pull-request.yaml
    """
    ghprb = XML.SubElement(xml_parent, 'org.jenkinsci.plugins.ghprb.'
                           'GhprbTrigger')
    XML.SubElement(ghprb, 'spec').text = data.get('cron', '')
    admin_string = "\n".join(data.get('admin-list', []))
    XML.SubElement(ghprb, 'adminlist').text = admin_string
    XML.SubElement(ghprb, 'allowMembersOfWhitelistedOrgsAsAdmin').text = str(
        data.get('allow-whitelist-orgs-as-admins', False)).lower()
    white_string = "\n".join(data.get('white-list', []))
    XML.SubElement(ghprb, 'whitelist').text = white_string
    org_string = "\n".join(data.get('org-list', []))
    XML.SubElement(ghprb, 'orgslist').text = org_string
    XML.SubElement(ghprb, 'cron').text = data.get('cron', '')

    build_desc_template = data.get('build-desc-template', '')
    if build_desc_template:
        XML.SubElement(ghprb, 'buildDescTemplate').text = str(
            build_desc_template)

    XML.SubElement(ghprb, 'triggerPhrase').text = \
        data.get('trigger-phrase', '')
    XML.SubElement(ghprb, 'onlyTriggerPhrase').text = str(
        data.get('only-trigger-phrase', False)).lower()
    XML.SubElement(ghprb, 'useGitHubHooks').text = str(
        data.get('github-hooks', False)).lower()
    XML.SubElement(ghprb, 'permitAll').text = str(
        data.get('permit-all', False)).lower()
    XML.SubElement(ghprb, 'autoCloseFailedPullRequests').text = str(
        data.get('auto-close-on-fail', False)).lower()

    white_list_target_branches = data.get('white-list-target-branches', [])
    if white_list_target_branches:
        ghprb_wltb = XML.SubElement(ghprb, 'whiteListTargetBranches')
        for branch in white_list_target_branches:
            be = XML.SubElement(ghprb_wltb, 'org.jenkinsci.plugins.'
                                'ghprb.GhprbBranch')
            XML.SubElement(be, 'branch').text = str(branch)

    auth_id = data.get('auth-id', '')
    if auth_id:
        XML.SubElement(ghprb, 'gitHubAuthId').text = str(auth_id)

    # PR status update fields
    status_context = data.get('status-context', '')
    triggered_status = data.get('triggered-status', '')
    started_status = data.get('started-status', '')
    status_url = data.get('status-url', '')
    status_add_test_results = data.get('status-add-test-results', '')
    success_status = data.get('success-status', '')
    failure_status = data.get('failure-status', '')
    error_status = data.get('error-status', '')

    # is status handling is required?
    requires_status = (
        status_context or
        triggered_status or
        started_status or
        status_url or
        status_add_test_results or
        success_status or
        failure_status or
        error_status
    )

    # is status message handling required?
    requires_status_message = (
        success_status or
        failure_status or
        error_status
    )

    # is comment handling required?
    success_comment = data.get('success-comment', '')
    failure_comment = data.get('failure-comment', '')
    error_comment = data.get('error-comment', '')
    requires_job_comment = (
        success_comment or
        failure_comment or
        error_comment
    )

    cancel_builds_on_update = data.get('cancel-builds-on-update', False)

    # We want to have only one 'extensions' subelement, even if status
    # handling, comment handling and other extensions are enabled.
    if requires_status or requires_job_comment or cancel_builds_on_update:
        extensions = XML.SubElement(ghprb, 'extensions')

    # Both comment and status elements have this same type.  Using a const is
    # much easier to read than repeating the tokens for this class each time
    # it's used
    comment_type = 'org.jenkinsci.plugins.ghprb.extensions.comments.'
    comment_type = comment_type + 'GhprbBuildResultMessage'

    if requires_status:
        simple_status = XML.SubElement(extensions,
                                       'org.jenkinsci.plugins'
                                       '.ghprb.extensions.status.'
                                       'GhprbSimpleStatus')
        if status_context:
            XML.SubElement(simple_status, 'commitStatusContext').text = str(
                status_context)
        if triggered_status:
            XML.SubElement(simple_status, 'triggeredStatus').text = str(
                triggered_status)
        if started_status:
            XML.SubElement(simple_status, 'startedStatus').text = str(
                started_status)
        if status_url:
            XML.SubElement(simple_status, 'statusUrl').text = str(
                status_url)
        if status_add_test_results:
            XML.SubElement(simple_status, 'addTestResults').text = str(
                status_add_test_results).lower()

        if requires_status_message:
            completed_elem = XML.SubElement(simple_status, 'completedStatus')
            if success_status:
                success_elem = XML.SubElement(completed_elem, comment_type)
                XML.SubElement(success_elem, 'message').text = str(
                    success_status)
                XML.SubElement(success_elem, 'result').text = 'SUCCESS'
            if failure_status:
                failure_elem = XML.SubElement(completed_elem, comment_type)
                XML.SubElement(failure_elem, 'message').text = str(
                    failure_status)
                XML.SubElement(failure_elem, 'result').text = 'FAILURE'
            if error_status:
                error_elem = XML.SubElement(completed_elem, comment_type)
                XML.SubElement(error_elem, 'message').text = str(error_status)
                XML.SubElement(error_elem, 'result').text = 'ERROR'

    # job comment handling
    if requires_job_comment:
        build_status = XML.SubElement(extensions,
                                      'org.jenkinsci.plugins.ghprb.extensions'
                                      '.comments.'
                                      'GhprbBuildStatus')
        messages_elem = XML.SubElement(build_status, 'messages')
        if success_comment:
            success_comment_elem = XML.SubElement(messages_elem, comment_type)
            XML.SubElement(success_comment_elem, 'message').text = str(
                success_comment)
            XML.SubElement(success_comment_elem, 'result').text = 'SUCCESS'
        if failure_comment:
            failure_comment_elem = XML.SubElement(messages_elem, comment_type)
            XML.SubElement(failure_comment_elem, 'message').text = str(
                failure_comment)
            XML.SubElement(failure_comment_elem, 'result').text = 'FAILURE'
        if error_comment:
            error_comment_elem = XML.SubElement(messages_elem, comment_type)
            XML.SubElement(error_comment_elem, 'message').text = str(
                error_comment)
            XML.SubElement(error_comment_elem, 'result').text = 'ERROR'

    if cancel_builds_on_update:
        XML.SubElement(extensions,
                       'org.jenkinsci.plugins.ghprb.extensions.'
                       'build.GhprbCancelBuildsOnUpdate')


def gitlab_merge_request(registry, xml_parent, data):
    """yaml: gitlab-merge-request
    Build merge requests in gitlab and report results.
    Requires the Jenkins :jenkins-wiki:`Gitlab MergeRequest Builder Plugin.
    <Gitlab+Merge+Request+Builder+Plugin>`.

    :arg string cron: cron syntax of when to run (required)
    :arg string project-path: gitlab-relative path to project (required)

    Example:

    .. literalinclude:: \
        /../../tests/triggers/fixtures/gitlab-merge-request.yaml
    """
    ghprb = XML.SubElement(xml_parent, 'org.jenkinsci.plugins.gitlab.'
                           'GitlabBuildTrigger')
    if not data.get('cron', None):
        raise jenkins_jobs.errors.JenkinsJobsException(
            'gitlab-merge-request is missing "cron"')
    if not data.get('project-path', None):
        raise jenkins_jobs.errors.JenkinsJobsException(
            'gitlab-merge-request is missing "project-path"')

    # Because of a design limitation in the GitlabBuildTrigger Jenkins plugin
    # both 'spec' and '__cron' have to be set to the same value to have them
    # take effect. Also, cron and projectPath are prefixed with underscores
    # in the plugin, but spec is not.
    XML.SubElement(ghprb, 'spec').text = data.get('cron')
    XML.SubElement(ghprb, '__cron').text = data.get('cron')
    XML.SubElement(ghprb, '__projectPath').text = data.get('project-path')


def gitlab(registry, xml_parent, data):
    """yaml: gitlab
    Makes Jenkins act like a GitLab CI server.
    Requires the Jenkins :jenkins-wiki:`GitLab Plugin
    <GitLab+Plugin>`.

    :arg bool trigger-push: Build on Push Events (default true)
    :arg bool trigger-merge-request: Build on Merge Request Events (default
        true)
    :arg str trigger-open-merge-request-push: Rebuild open Merge Requests
        on Push Events.

        :trigger-open-merge-request-push values (< 1.1.26):
            * **true** (default)
            * **false**
        :trigger-open-merge-request-push values (>= 1.1.26):
            * **never** (default)
            * **source**
            * **both**
    :arg bool trigger-note: Build when comment is added with defined phrase
        (>= 1.2.4) (default true)
    :arg str note-regex: Phrase that triggers the build (>= 1.2.4) (default
        'Jenkins please retry a build')
    :arg bool ci-skip: Enable skipping builds of commits that contain
        [ci-skip] in the commit message (default true)
    :arg bool wip-skip: Enable skipping builds of WIP Merge Requests (>= 1.2.4)
        (default false)
    :arg bool set-build-description: Set build description to build cause
        (eg. Merge request or Git Push) (default true)
    :arg bool add-note-merge-request: Add note with build status on
        merge requests (default true)
    :arg bool add-vote-merge-request: Vote added to note with build status
        on merge requests (>= 1.1.27) (default true)
    :arg bool accept-merge-request-on-success: Automatically accept the Merge
        Request if the build is successful (>= 1.1.27) (default false)
    :arg bool add-ci-message: Add CI build status (1.1.28 - 1.2.0) (default
        false)
    :arg bool allow-all-branches: Allow all branches (Ignoring Filtered
        Branches) (< 1.1.29) (default false)
    :arg str branch-filter-type: Filter branches that can trigger a build.
        Valid values and their additional attributes are described in the
        `branch filter type`_ table (>= 1.1.29) (default 'All').
    :arg list include-branches: Defined list of branches to include
        (default [])
    :arg list exclude-branches: Defined list of branches to exclude
        (default [])
    :arg str target-branch-regex: Regular expression to select branches

    .. _`branch filter type`:

    ================== ====================================================
    Branch filter type Description
    ================== ====================================================
    All                All branches are allowed to trigger this job.
    NameBasedFilter    Filter branches by name.
                       List source branches that are allowed to trigger a
                       build from a Push event or a Merge Request event. If
                       both fields are left empty, all branches are allowed
                       to trigger this job. For Merge Request events only
                       the target branch name is filtered out by the
                       **include-branches** and **exclude-branches** lists.

    RegexBasedFilter   Filter branches by regex
                       The target branch regex allows to limit the
                       execution of this job to certain branches. Any
                       branch matching the specified pattern in
                       **target-branch-regex** triggers the job. No
                       filtering is performed if the field is left empty.
    ================== ====================================================

    Example (version < 1.1.26):

    .. literalinclude:: /../../tests/triggers/fixtures/gitlab001.yaml
       :language: yaml

    Minimal example (version >= 1.1.26):

    .. literalinclude:: /../../tests/triggers/fixtures/gitlab005.yaml
       :language: yaml

    Full example (version >= 1.1.26):

    .. literalinclude:: /../../tests/triggers/fixtures/gitlab004.yaml
       :language: yaml
    """
    def _add_xml(elem, name, value):
        XML.SubElement(elem, name).text = value

    gitlab = XML.SubElement(
        xml_parent, 'com.dabsquared.gitlabjenkins.GitLabPushTrigger'
    )
    plugin_info = registry.get_plugin_info('GitLab Plugin')
    plugin_ver = pkg_resources.parse_version(plugin_info.get('version', "0"))
    valid_merge_request = ['never', 'source', 'both']

    if plugin_ver >= pkg_resources.parse_version("1.1.26"):
        mapping = [
            ('trigger-open-merge-request-push',
             'triggerOpenMergeRequestOnPush', 'never', valid_merge_request)]
        convert_mapping_to_xml(gitlab, data, mapping, fail_required=True)
    else:
        mapping = [
            ('trigger-open-merge-request-push',
             'triggerOpenMergeRequestOnPush', True)]
        convert_mapping_to_xml(gitlab, data, mapping, fail_required=True)

    if plugin_ver == pkg_resources.parse_version('1.1.29'):
        if data.get('branch-filter-type', '') == 'All':
            data['branch-filter-type'] = ''
        valid_filters = ['', 'NameBasedFilter', 'RegexBasedFilter']
        mapping = [
            ('branch-filter-type', 'branchFilterName', '', valid_filters)]
        convert_mapping_to_xml(gitlab, data, mapping, fail_required=True)
    else:
        valid_filters = ['All', 'NameBasedFilter', 'RegexBasedFilter']
        mapping = [
            ('branch-filter-type', 'branchFilterType', 'All', valid_filters)]
        convert_mapping_to_xml(gitlab, data, mapping, fail_required=True)

    XML.SubElement(gitlab, 'spec').text = ''
    mapping = [
        ('trigger-push', 'triggerOnPush', True),
        ('trigger-merge-request', 'triggerOnMergeRequest', True),
        ('trigger-note', 'triggerOnNoteRequest', True),
        ('note-regex', 'noteRegex', 'Jenkins please retry a build'),
        ('ci-skip', 'ciSkip', True),
        ('wip-skip', 'skipWorkInProgressMergeRequest', True),
        ('set-build-description', 'setBuildDescription', True),
        ('add-note-merge-request', 'addNoteOnMergeRequest', True),
        ('add-vote-merge-request', 'addVoteOnMergeRequest', True),
        ('accept-merge-request-on-success', 'acceptMergeRequestOnSuccess',
         False),
        ('add-ci-message', 'addCiMessage', False),
        ('allow-all-branches', 'allowAllBranches', False),
        ('target-branch-regex', 'targetBranchRegex', '')
    ]

    list_mapping = (
        ('include-branches', 'includeBranchesSpec', []),
        ('exclude-branches', 'excludeBranchesSpec', []),
    )
    convert_mapping_to_xml(gitlab, data, mapping, fail_required=True)

    for yaml_name, xml_name, default_val in list_mapping:
        value = ', '.join(data.get(yaml_name, default_val))
        _add_xml(gitlab, xml_name, value)


def build_result(registry, xml_parent, data):
    """yaml: build-result
    Configure jobB to monitor jobA build result. A build is scheduled if there
    is a new build result that matches your criteria (unstable, failure, ...).
    Requires the Jenkins :jenkins-wiki:`BuildResultTrigger Plugin
    <BuildResultTrigger+Plugin>`.

    :arg list groups: List groups of jobs and results to monitor for
    :arg list jobs: The jobs to monitor (required)
    :arg list results: Build results to monitor for (default success)
    :arg bool combine: Combine all job information.  A build will be
        scheduled only if all conditions are met (default false)
    :arg str cron: The cron syntax with which to poll the jobs for the
        supplied result (default '')

    Example::

      triggers:
        - build-result:
            combine: true
            cron: '* * * * *'
            groups:
              - jobs:
                  - foo
                  - example
                results:
                  - unstable
              - jobs:
                  - foo2
                results:
                  - not-built
                  - aborted
    """
    brt = XML.SubElement(xml_parent, 'org.jenkinsci.plugins.'
                         'buildresulttrigger.BuildResultTrigger')
    XML.SubElement(brt, 'spec').text = data.get('cron', '')
    XML.SubElement(brt, 'combinedJobs').text = str(
        data.get('combine', False)).lower()
    jobs_info = XML.SubElement(brt, 'jobsInfo')
    result_dict = {'success': 'SUCCESS',
                   'unstable': 'UNSTABLE',
                   'failure': 'FAILURE',
                   'not-built': 'NOT_BUILT',
                   'aborted': 'ABORTED'}
    for group in data['groups']:
        brti = XML.SubElement(jobs_info, 'org.jenkinsci.plugins.'
                              'buildresulttrigger.model.'
                              'BuildResultTriggerInfo')
        if not group.get('jobs', []):
            raise jenkins_jobs.errors.\
                JenkinsJobsException('Jobs is missing and a required'
                                     ' element')
        jobs_string = ",".join(group['jobs'])
        XML.SubElement(brti, 'jobNames').text = jobs_string
        checked_results = XML.SubElement(brti, 'checkedResults')
        for result in group.get('results', ['success']):
            if result not in result_dict:
                raise jenkins_jobs.errors.\
                    JenkinsJobsException('Result entered is not valid,'
                                         ' must be one of: '
                                         + ', '.join(result_dict.keys()))
            model_checked = XML.SubElement(checked_results, 'org.jenkinsci.'
                                           'plugins.buildresulttrigger.model.'
                                           'CheckedResult')
            XML.SubElement(model_checked, 'checked').text = result_dict[result]


def reverse(registry, xml_parent, data):
    """yaml: reverse
    This trigger can be configured in the UI using the checkbox with the
    following text: 'Build after other projects are built'.

    Set up a trigger so that when some other projects finish building, a new
    build is scheduled for this project. This is convenient for running an
    extensive test after a build is complete, for example.

    This configuration complements the "Build other projects" section in the
    "Post-build Actions" of an upstream project, but is preferable when you
    want to configure the downstream project.

    :arg str jobs: List of jobs to watch. Can be either a comma separated
      list or a list.
    :arg str result: Build results to monitor for between the following
      options: success, unstable and failure. (default 'success').

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/reverse.yaml

    Example List:

    .. literalinclude:: /../../tests/triggers/fixtures/reverse-list.yaml
    """
    reserveBuildTrigger = XML.SubElement(
        xml_parent, 'jenkins.triggers.ReverseBuildTrigger')

    supported_thresholds = ['SUCCESS', 'UNSTABLE', 'FAILURE']

    XML.SubElement(reserveBuildTrigger, 'spec').text = ''

    jobs = data.get('jobs')
    if isinstance(jobs, list):
        jobs = ",".join(jobs)
    XML.SubElement(reserveBuildTrigger, 'upstreamProjects').text = \
        jobs

    threshold = XML.SubElement(reserveBuildTrigger, 'threshold')
    result = str(data.get('result', 'success')).upper()
    if result not in supported_thresholds:
        raise jenkins_jobs.errors.JenkinsJobsException(
            "Choice should be one of the following options: %s." %
            ", ".join(supported_thresholds))
    XML.SubElement(threshold, 'name').text = \
        hudson_model.THRESHOLDS[result]['name']
    XML.SubElement(threshold, 'ordinal').text = \
        hudson_model.THRESHOLDS[result]['ordinal']
    XML.SubElement(threshold, 'color').text = \
        hudson_model.THRESHOLDS[result]['color']
    XML.SubElement(threshold, 'completeBuild').text = \
        str(hudson_model.THRESHOLDS[result]['complete']).lower()


def monitor_folders(registry, xml_parent, data):
    """yaml: monitor-folders
    Configure Jenkins to monitor folders.
    Requires the Jenkins :jenkins-wiki:`Filesystem Trigger Plugin
    <FSTrigger+Plugin>`.

    :arg str path: Folder path to poll. (default '')
    :arg list includes: Fileset includes setting that specifies the list of
      includes files. Basedir of the fileset is relative to the workspace
      root. If no value is set, all files are used. (default '')
    :arg str excludes: The 'excludes' pattern. A file that matches this mask
      will not be polled even if it matches the mask specified in 'includes'
      section. (default '')
    :arg bool check-modification-date: Check last modification date.
      (default true)
    :arg bool check-content: Check content. (default true)
    :arg bool check-fewer: Check fewer files (default true)
    :arg str cron: cron syntax of when to run (default '')

    Full Example:

    .. literalinclude::
       /../../tests/triggers/fixtures/monitor-folders-full.yaml
       :language: yaml

    Minimal Example:

    .. literalinclude::
       /../../tests/triggers/fixtures/monitor-folders-minimal.yaml
       :language: yaml
    """
    ft = XML.SubElement(xml_parent, ('org.jenkinsci.plugins.fstrigger.'
                                     'triggers.FolderContentTrigger'))
    ft.set('plugin', 'fstrigger')

    mappings = [
        ('path', 'path', ''),
        ('cron', 'spec', ''),
    ]
    convert_mapping_to_xml(ft, data, mappings, fail_required=True)

    includes = data.get('includes', '')
    XML.SubElement(ft, 'includes').text = ",".join(includes)
    XML.SubElement(ft, 'excludes').text = data.get('excludes', '')
    XML.SubElement(ft, 'excludeCheckLastModificationDate').text = str(
        not data.get('check-modification-date', True)).lower()
    XML.SubElement(ft, 'excludeCheckContent').text = str(
        not data.get('check-content', True)).lower()
    XML.SubElement(ft, 'excludeCheckFewerOrMoreFiles').text = str(
        not data.get('check-fewer', True)).lower()


def monitor_files(registry, xml_parent, data):
    """yaml: monitor-files
    Configure Jenkins to monitor files.
    Requires the Jenkins :jenkins-wiki:`Filesystem Trigger Plugin
    <FSTrigger+Plugin>`.

    :arg list files: List of files to monitor

        :File:
            * **path** (`str`) -- File path to monitor. You can use a pattern
              that specifies a set of files if you dont know the real file
              path. (required)
            * **strategy** (`str`) -- Choose your strategy if there is more
              than one matching file. Can be one of Ignore file ('IGNORE') or
              Use the most recent ('LATEST'). (default 'LATEST')
            * **check-content** (`list`) -- List of content changes of the
              file to monitor

                :Content Nature:
                    * **simple** (`bool`) -- Trigger on change in content of
                      the specified file (whatever the type file).
                      (default false)
                    * **jar** (`bool`) -- Trigger on change in content of the
                      specified JAR file. (default false)
                    * **tar** (`bool`) -- Trigger on change in content of the
                      specified Tar file. (default false)
                    * **zip** (`bool`) -- Trigger on change in content of the
                      specified ZIP file. (default false)
                    * **source-manifest** (`list`) -- Trigger on change to
                      MANIFEST files.

                        :MANIFEST File:
                            * **keys** (`list`) -- List of keys to inspect.
                              (optional)
                            * **all-keys** (`bool`) -- If true, take into
                              account all keys. (default true)

                    * **jar-manifest** (`list`) -- Trigger on change to
                      MANIFEST files (contained in jar files).

                        :MANIFEST File:
                            * **keys** (`list`) -- List of keys to inspect.
                              (optional)
                            * **all-keys** (`bool`) -- If true, take into
                              account all keys. (default true)

                    * **properties** (`list`) -- Monitor the contents of the
                      properties file.

                        :Properties File:
                            * **keys** (`list`) -- List of keys to inspect.
                              (optional)
                            * **all-keys** (`bool`) -- If true, take into
                              account all keys. (default true)

                    * **xml** (`list str`) -- Trigger on change to the listed
                      XPath expressions.
                    * **text** (`list str`) -- Trigger on change to the listed
                      regular expressions.

             * **ignore-modificaton-date** (`bool`) -- If true, ignore the file
               modification date. Only valid when content changes of the file
               are being monitored. (default true)
    :arg str cron: cron syntax of when to run (default '')

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/monitor-files001.yaml
       :language: yaml
    """
    ft_prefix = 'org.jenkinsci.plugins.fstrigger.triggers.'
    valid_strategies = ['LATEST', 'IGNORE']
    valid_content_types = {
        'simple': ['Simple', '', '', []],
        'jar': ['JAR', '', '', []],
        'tar': ['Tar', '', '', []],
        'zip': ['ZIP', '', '', []],
        'source-manifest': ['SourceManifest'],
        'jar-manifest': ['JARManifest'],
        'properties': ['Properties'],
        'xml': ['XML', 'expressions', 'expression', None],
        'text': ['Text', 'regexElements', 'regex', None]
    }

    ft = XML.SubElement(xml_parent, ft_prefix + 'FileNameTrigger')
    XML.SubElement(ft, 'spec').text = str(data.get('cron', ''))
    files = data.get('files', [])
    if not files:
        raise JenkinsJobsException('At least one file must be provided')

    files_tag = XML.SubElement(ft, 'fileInfo')
    for file_info in files:
        file_tag = XML.SubElement(files_tag, ft_prefix + 'FileNameTriggerInfo')
        try:
            XML.SubElement(file_tag,
                           'filePathPattern').text = file_info['path']
        except KeyError:
            raise MissingAttributeError('path')

        strategy = file_info.get('strategy', 'LATEST')
        if strategy not in valid_strategies:
            raise InvalidAttributeError('strategy', strategy, valid_strategies)
        XML.SubElement(file_tag, 'strategy').text = strategy
        check_content = file_info.get('check-content', [])
        XML.SubElement(file_tag, 'inspectingContentFile').text = str(
            bool(check_content)).lower()

        base_content_tag = XML.SubElement(file_tag, 'contentFileTypes')
        for content in check_content:
            type_name = next(iter(content.keys()))
            if type_name not in valid_content_types:
                raise InvalidAttributeError('check-content', type_name,
                                            valid_content_types.keys())
            content_type = valid_content_types.get(type_name)
            if len(content_type) == 1:
                class_name = '{0}filecontent.{1}FileContent'.format(
                    ft_prefix, content_type[0])
                content_data = content.get(type_name)
                if not content_data:
                    raise JenkinsJobsException("Need to specify something "
                                               "under " + type_name)
                for entry in content_data:
                    content_tag = XML.SubElement(base_content_tag, class_name)
                    keys = entry.get('keys', [])
                    if keys:
                        XML.SubElement(content_tag, 'keys2Inspect'
                                       ).text = ",".join(keys)
                    XML.SubElement(content_tag, 'allKeys').text = str(
                        entry.get('all-keys', True)).lower()
            else:
                if content[type_name]:
                    sub_entries = content_type[3]
                    if sub_entries is None:
                        sub_entries = content[type_name]
                    build_content_type(base_content_tag, sub_entries,
                                       ft_prefix + 'filecontent',
                                       'FileContent', 'FileContentEntry',
                                       *content_type[0:3])
        if bool(check_content):
            XML.SubElement(file_tag,
                           'doNotCheckLastModificationDate').text = str(
                file_info.get('ignore-modificaton-date', True)).lower()


def ivy(registry, xml_parent, data):
    """yaml: ivy
    Poll with an Ivy script
    Requires the Jenkins :jenkins-wiki:`IvyTrigger Plugin
    <IvyTrigger+Plugin>`.

    :arg str path: Path of the ivy file. (optional)
    :arg str settings-path: Ivy Settings Path. (optional)
    :arg list str properties-file: List of properties file path. Properties
      will be injected as variables in the ivy settings file. (optional)
    :arg str properties-content: Properties content. Properties will be
      injected as variables in the ivy settings file. (optional)
    :arg bool debug: Active debug mode on artifacts resolution. (default false)
    :arg download-artifacts: Download artifacts for dependencies to see if they
      have changed. (default true)
    :arg bool enable-concurrent: Enable Concurrent Build. (default false)
    :arg str label: Restrict where the polling should run. (default '')
    :arg str cron: cron syntax of when to run (default '')

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/ivy.yaml
    """
    it = XML.SubElement(xml_parent,
                        'org.jenkinsci.plugins.ivytrigger.IvyTrigger')
    mappings = [('path', 'ivyPath', None),
                ('settings-path', 'ivySettingsPath', None),
                ('properties-file', 'propertiesFilePath', None),
                ('properties-content', 'propertiesContent', None),
                ('debug', 'debug', False),
                ('download-artifacts', 'downloadArtifacts', True),
                ('enable-concurrent', 'enableConcurrentBuild', False),
                ('cron', 'spec', '')]
    for prop in mappings:
        opt, xmlopt, default_val = prop[:3]
        val = data.get(opt, default_val)
        if val is not None:
            if type(val) == bool:
                val = str(val).lower()
            if type(val) == list:
                val = ";".join(val)
            XML.SubElement(it, xmlopt).text = val
    label = data.get('label')
    XML.SubElement(it, 'labelRestriction').text = str(bool(label)).lower()
    if label:
        XML.SubElement(it, 'triggerLabel').text = label


def script(registry, xml_parent, data):
    """yaml: script
    Triggers the job using shell or batch script.
    Requires the Jenkins :jenkins-wiki:`ScriptTrigger Plugin
    <ScriptTrigger+Plugin>`.

    :arg str label: Restrict where the polling should run. (default '')
    :arg str script: A shell or batch script. (default '')
    :arg str script-file-path: A shell or batch script path. (default '')
    :arg str cron: cron syntax of when to run (default '')
    :arg bool enable-concurrent:  Enables triggering concurrent builds.
                                  (default false)
    :arg int exit-code:  If the exit code of the script execution returns this
                         expected exit code, a build is scheduled. (default 0)

    Full Example:

    .. literalinclude:: /../../tests/triggers/fixtures/script-full.yaml
       :language: yaml

    Minimal Example:

    .. literalinclude:: /../../tests/triggers/fixtures/script-minimal.yaml
       :language: yaml
    """
    st = XML.SubElement(
        xml_parent,
        'org.jenkinsci.plugins.scripttrigger.ScriptTrigger'
    )
    st.set('plugin', 'scripttrigger')
    label = data.get('label')
    mappings = [
        ('script', 'script', ''),
        ('script-file-path', 'scriptFilePath', ''),
        ('cron', 'spec', ''),
        ('enable-concurrent', 'enableConcurrentBuild', False),
        ('exit-code', 'exitCode', 0)
    ]
    convert_mapping_to_xml(st, data, mappings, fail_required=True)

    XML.SubElement(st, 'labelRestriction').text = str(bool(label)).lower()
    if label:
        XML.SubElement(st, 'triggerLabel').text = label


def groovy_script(registry, xml_parent, data):
    """yaml: groovy-script
    Triggers the job using a groovy script.
    Requires the Jenkins :jenkins-wiki:`ScriptTrigger Plugin
    <ScriptTrigger+Plugin>`.

    :arg bool system-script: If true, run the groovy script as a system script,
      the script will have access to the same variables as the Groovy Console.
      If false, run the groovy script on the executor node, the script will not
      have access to the hudson or job model. (default false)
    :arg str script: Content of the groovy script. If the script result is
      evaluated to true, a build is scheduled. (default '')
    :arg str script-file-path: Groovy script path. (default '')
    :arg str property-file-path: Property file path. All properties will be set
      as parameters for the triggered build. (default '')
    :arg bool enable-concurrent: Enable concurrent build. (default false)
    :arg str label: Restrict where the polling should run. (default '')
    :arg str cron: cron syntax of when to run (default '')

    Full Example:

    .. literalinclude:: /../../tests/triggers/fixtures/groovy-script-full.yaml
       :language: yaml

    Minimal Example:

    .. literalinclude::
        /../../tests/triggers/fixtures/groovy-script-minimal.yaml
       :language: yaml
    """
    gst = XML.SubElement(
        xml_parent,
        'org.jenkinsci.plugins.scripttrigger.groovy.GroovyScriptTrigger'
    )
    gst.set('plugin', 'scripttrigger')

    mappings = [
        ('system-script', 'groovySystemScript', False),
        ('script', 'groovyExpression', ''),
        ('script-file-path', 'groovyFilePath', ''),
        ('property-file-path', 'propertiesFilePath', ''),
        ('enable-concurrent', 'enableConcurrentBuild', False),
        ('cron', 'spec', ''),
    ]
    convert_mapping_to_xml(gst, data, mappings, fail_required=True)

    label = data.get('label')
    XML.SubElement(gst, 'labelRestriction').text = str(bool(label)).lower()
    if label:
        XML.SubElement(gst, 'triggerLabel').text = label


def rabbitmq(registry, xml_parent, data):
    """yaml: rabbitmq
    This plugin triggers build using remote build message in RabbitMQ queue.
    Requires the Jenkins :jenkins-wiki:`RabbitMQ Build Trigger Plugin
    <RabbitMQ+Build+Trigger+Plugin>`.

    :arg str token: the build token expected in the message queue (required)

    Example:

    .. literalinclude:: /../../tests/triggers/fixtures/rabbitmq.yaml
       :language: yaml
    """

    rabbitmq = XML.SubElement(
        xml_parent,
        'org.jenkinsci.plugins.rabbitmqbuildtrigger.'
        'RemoteBuildTrigger')

    XML.SubElement(rabbitmq, 'spec').text = ''

    try:
        XML.SubElement(rabbitmq, 'remoteBuildToken').text = str(
            data.get('token'))
    except KeyError as e:
        raise MissingAttributeError(e.arg[0])


def parameterized_timer(parser, xml_parent, data):
    """yaml: parameterized-timer
    Trigger builds with parameters at certain times.
    Requires the Jenkins :jenkins-wiki:`Parameterized Scheduler Plugin
    <Parameterized+Scheduler+Plugin>`.

    :arg str cron: cron syntax of when to run and with which parameters
        (required)

    Example:

    .. literalinclude::
        /../../tests/triggers/fixtures/parameterized-timer001.yaml
       :language: yaml
    """

    param_timer = XML.SubElement(
        xml_parent,
        'org.jenkinsci.plugins.parameterizedscheduler.'
        'ParameterizedTimerTrigger')

    XML.SubElement(param_timer, 'spec').text = ''

    try:
        XML.SubElement(param_timer, 'parameterizedSpecification').text = str(
            data.get('cron'))
    except KeyError as e:
        raise MissingAttributeError(e)


class Triggers(jenkins_jobs.modules.base.Base):
    sequence = 50

    component_type = 'trigger'
    component_list_type = 'triggers'

    def gen_xml(self, xml_parent, data):
        triggers = data.get('triggers', [])
        if not triggers:
            return

        trig_e = XML.SubElement(xml_parent, 'triggers', {'class': 'vector'})
        for trigger in triggers:
            self.registry.dispatch('trigger', trig_e, trigger)

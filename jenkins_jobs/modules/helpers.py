# Copyright 2015 Thanh Ha
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

import xml.etree.ElementTree as XML

from jenkins_jobs.errors import InvalidAttributeError
from jenkins_jobs.errors import JenkinsJobsException
from jenkins_jobs.errors import MissingAttributeError


def build_trends_publisher(plugin_name, xml_element, data):
    """Helper to create various trend publishers.
    """

    def append_thresholds(element, data, only_totals):
        """Appends the status thresholds.
        """

        for status in ['unstable', 'failed']:
            status_data = data.get(status, {})

            limits = [
                ('total-all', 'TotalAll'),
                ('total-high', 'TotalHigh'),
                ('total-normal', 'TotalNormal'),
                ('total-low', 'TotalLow')]

            if only_totals is False:
                limits.extend([
                    ('new-all', 'NewAll'),
                    ('new-high', 'NewHigh'),
                    ('new-normal', 'NewNormal'),
                    ('new-low', 'NewLow')])

            for key, tag_suffix in limits:
                tag_name = status + tag_suffix
                XML.SubElement(element, tag_name).text = str(
                    status_data.get(key, ''))

    # Tuples containing: setting name, tag name, default value
    settings = [
        ('healthy', 'healthy', ''),
        ('unhealthy', 'unHealthy', ''),
        ('health-threshold', 'thresholdLimit', 'low'),
        ('plugin-name', 'pluginName', plugin_name),
        ('default-encoding', 'defaultEncoding', ''),
        ('can-run-on-failed', 'canRunOnFailed', False),
        ('use-stable-build-as-reference', 'useStableBuildAsReference', False),
        ('use-previous-build-as-reference',
         'usePreviousBuildAsReference', False),
        ('use-delta-values', 'useDeltaValues', False),
        ('thresholds', 'thresholds', {}),
        ('should-detect-modules', 'shouldDetectModules', False),
        ('dont-compute-new', 'dontComputeNew', True),
        ('do-not-resolve-relative-paths', 'doNotResolveRelativePaths', False),
        ('pattern', 'pattern', '')]

    thresholds = ['low', 'normal', 'high']

    for key, tag_name, default in settings:
        xml_config = XML.SubElement(xml_element, tag_name)
        config_value = data.get(key, default)

        if key == 'thresholds':
            append_thresholds(
                xml_config,
                config_value,
                data.get('dont-compute-new', True))
        elif key == 'health-threshold' and config_value not in thresholds:
            raise JenkinsJobsException("health-threshold must be one of %s" %
                                       ", ".join(thresholds))
        else:
            if isinstance(default, bool):
                xml_config.text = str(config_value).lower()
            else:
                xml_config.text = str(config_value)


def config_file_provider_builder(xml_parent, data):
    """Builder / Wrapper helper"""
    xml_files = XML.SubElement(xml_parent, 'managedFiles')

    files = data.get('files', [])
    for file in files:
        xml_file = XML.SubElement(xml_files, 'org.jenkinsci.plugins.'
                                  'configfiles.buildwrapper.ManagedFile')
        mapping = [
            ('file-id', 'fileId', None),
            ('target', 'targetLocation', ''),
            ('variable', 'variable', ''),
        ]
        convert_mapping_to_xml(xml_file, file, mapping, fail_required=True)


def config_file_provider_settings(xml_parent, data):
    SETTINGS_TYPES = ['file', 'cfp']
    settings = {
        'default-settings':
        'jenkins.mvn.DefaultSettingsProvider',
        'settings':
        'jenkins.mvn.FilePathSettingsProvider',
        'config-file-provider-settings':
        'org.jenkinsci.plugins.configfiles.maven.job.MvnSettingsProvider',
        'default-global-settings':
        'jenkins.mvn.DefaultGlobalSettingsProvider',
        'global-settings':
        'jenkins.mvn.FilePathGlobalSettingsProvider',
        'config-file-provider-global-settings':
        'org.jenkinsci.plugins.configfiles.maven.job.'
        'MvnGlobalSettingsProvider',
    }

    if 'settings' in data:
        # Support for Config File Provider
        settings_file = str(data['settings'])
        settings_type = data.get('settings-type', 'file')

        # For cfp versions <2.10.0 we are able to detect cfp via the config
        # settings name.
        text = 'org.jenkinsci.plugins.configfiles.maven.MavenSettingsConfig'
        if settings_file.startswith(text):
            settings_type = 'cfp'

        if settings_type == 'file':
            lsettings = XML.SubElement(
                xml_parent, 'settings',
                {'class': settings['settings']})
            XML.SubElement(lsettings, 'path').text = settings_file
        elif settings_type == 'cfp':
            lsettings = XML.SubElement(
                xml_parent, 'settings',
                {'class': settings['config-file-provider-settings']})
            XML.SubElement(lsettings, 'settingsConfigId').text = settings_file
        else:
            raise InvalidAttributeError(
                'settings-type', settings_type, SETTINGS_TYPES)
    else:
        XML.SubElement(xml_parent, 'settings',
                       {'class': settings['default-settings']})

    if 'global-settings' in data:
        # Support for Config File Provider
        global_settings_file = str(data['global-settings'])
        global_settings_type = data.get('settings-type', 'file')

        # For cfp versions <2.10.0 we are able to detect cfp via the config
        # settings name.
        text = ('org.jenkinsci.plugins.configfiles.maven.'
                'GlobalMavenSettingsConfig')
        if global_settings_file.startswith(text):
            global_settings_type = 'cfp'

        if global_settings_type == 'file':
            gsettings = XML.SubElement(xml_parent, 'globalSettings',
                                       {'class': settings['global-settings']})
            XML.SubElement(gsettings, 'path').text = global_settings_file
        elif global_settings_type == 'cfp':
            gsettings = XML.SubElement(
                xml_parent, 'globalSettings',
                {'class': settings['config-file-provider-global-settings']})
            XML.SubElement(
                gsettings,
                'settingsConfigId').text = global_settings_file
        else:
            raise InvalidAttributeError(
                'settings-type', global_settings_type, SETTINGS_TYPES)
    else:
        XML.SubElement(xml_parent, 'globalSettings',
                       {'class': settings['default-global-settings']})


def copyartifact_build_selector(xml_parent, data, select_tag='selector'):

    select = data.get('which-build', 'last-successful')
    selectdict = {'last-successful': 'StatusBuildSelector',
                  'last-completed': 'LastCompletedBuildSelector',
                  'specific-build': 'SpecificBuildSelector',
                  'last-saved': 'SavedBuildSelector',
                  'upstream-build': 'TriggeredBuildSelector',
                  'permalink': 'PermalinkBuildSelector',
                  'workspace-latest': 'WorkspaceSelector',
                  'build-param': 'ParameterizedBuildSelector',
                  'downstream-build': 'DownstreamBuildSelector',
                  'multijob-build': 'MultiJobBuildSelector'}
    if select not in selectdict:
        raise InvalidAttributeError('which-build',
                                    select,
                                    selectdict.keys())
    permalink = data.get('permalink', 'last')
    permalinkdict = {'last': 'lastBuild',
                     'last-stable': 'lastStableBuild',
                     'last-successful': 'lastSuccessfulBuild',
                     'last-failed': 'lastFailedBuild',
                     'last-unstable': 'lastUnstableBuild',
                     'last-unsuccessful': 'lastUnsuccessfulBuild'}
    if permalink not in permalinkdict:
        raise InvalidAttributeError('permalink',
                                    permalink,
                                    permalinkdict.keys())
    if select == 'multijob-build':
        selector = XML.SubElement(xml_parent, select_tag,
                                  {'class':
                                   'com.tikal.jenkins.plugins.multijob.' +
                                      selectdict[select]})
    else:
        selector = XML.SubElement(xml_parent, select_tag,
                                  {'class':
                                   'hudson.plugins.copyartifact.' +
                                      selectdict[select]})
    if select == 'specific-build':
        XML.SubElement(selector, 'buildNumber').text = data['build-number']
    if select == 'last-successful':
        XML.SubElement(selector, 'stable').text = str(
            data.get('stable', False)).lower()
    if select == 'upstream-build':
        XML.SubElement(selector, 'fallbackToLastSuccessful').text = str(
            data.get('fallback-to-last-successful', False)).lower()
    if select == 'permalink':
        XML.SubElement(selector, 'id').text = permalinkdict[permalink]
    if select == 'build-param':
        XML.SubElement(selector, 'parameterName').text = data['param']
    if select == 'downstream-build':
        XML.SubElement(selector, 'upstreamProjectName').text = (
            data['upstream-project-name'])
        XML.SubElement(selector, 'upstreamBuildNumber').text = (
            data['upstream-build-number'])


def findbugs_settings(xml_parent, data):
    # General Options
    mapping = [
        ('rank-priority', 'isRankActivated', False),
        ('include-files', 'includePattern', ''),
        ('exclude-files', 'excludePattern', ''),
    ]
    convert_mapping_to_xml(xml_parent, data, mapping, fail_required=True)


def get_value_from_yaml_or_config_file(key, section, data, jjb_config):
    result = data.get(key, '')
    if result == '':
        result = jjb_config.get_plugin_config(section, key)
    return result


def cloudformation_region_dict():
    region_dict = {'us-east-1': 'US_East_Northern_Virginia',
                   'us-west-1': 'US_WEST_Northern_California',
                   'us-west-2': 'US_WEST_Oregon',
                   'eu-central-1': 'EU_Frankfurt',
                   'eu-west-1': 'EU_Ireland',
                   'ap-southeast-1': 'Asia_Pacific_Singapore',
                   'ap-southeast-2': 'Asia_Pacific_Sydney',
                   'ap-northeast-1': 'Asia_Pacific_Tokyo',
                   'sa-east-1': 'South_America_Sao_Paulo'}
    return region_dict


def cloudformation_init(xml_parent, data, xml_tag):
    cloudformation = XML.SubElement(
        xml_parent, 'com.syncapse.jenkinsci.'
                    'plugins.awscloudformationwrapper.' + xml_tag)
    return XML.SubElement(cloudformation, 'stacks')


def cloudformation_stack(xml_parent, stack, xml_tag, stacks, region_dict):
    if 'name' not in stack or stack['name'] == '':
        raise MissingAttributeError('name')
    step = XML.SubElement(
        stacks, 'com.syncapse.jenkinsci.plugins.'
                'awscloudformationwrapper.' + xml_tag)
    try:
        XML.SubElement(step, 'stackName').text = stack['name']
        XML.SubElement(step, 'awsAccessKey').text = stack['access-key']
        XML.SubElement(step, 'awsSecretKey').text = stack['secret-key']
        region = stack['region']
    except KeyError as e:
        raise MissingAttributeError(e.args[0])
    if region not in region_dict:
        raise InvalidAttributeError('region', region, region_dict.keys())
    XML.SubElement(step, 'awsRegion').text = region_dict.get(region)
    if xml_tag == 'SimpleStackBean':
        prefix = str(stack.get('prefix', False)).lower()
        XML.SubElement(step, 'isPrefixSelected').text = prefix
    else:
        XML.SubElement(step, 'description').text = stack.get('description', '')
        XML.SubElement(step, 'parameters').text = ','.join(
            stack.get('parameters', []))
        XML.SubElement(step, 'timeout').text = str(stack.get('timeout', '0'))
        XML.SubElement(step, 'sleep').text = str(stack.get('sleep', '0'))
        try:
            XML.SubElement(step, 'cloudFormationRecipe').text = stack['recipe']
        except KeyError as e:
            raise MissingAttributeError(e.args[0])


def include_exclude_patterns(xml_parent, data, yaml_prefix,
                             xml_elem_name):
    xml_element = XML.SubElement(xml_parent, xml_elem_name)
    XML.SubElement(xml_element, 'includePatterns').text = ','.join(
        data.get(yaml_prefix + '-include-patterns', []))
    XML.SubElement(xml_element, 'excludePatterns').text = ','.join(
        data.get(yaml_prefix + '-exclude-patterns', []))


def artifactory_deployment_patterns(xml_parent, data):
    include_exclude_patterns(xml_parent, data, 'deployment',
                             'artifactDeploymentPatterns')


def artifactory_env_vars_patterns(xml_parent, data):
    include_exclude_patterns(xml_parent, data, 'env-vars',
                             'envVarsPatterns')


def artifactory_optional_props(xml_parent, data, target):
    optional_str_props = [
        ('scopes', 'scopes'),
        ('violationRecipients', 'violation-recipients'),
        ('blackDuckAppName', 'black-duck-app-name'),
        ('blackDuckAppVersion', 'black-duck-app-version'),
        ('blackDuckReportRecipients', 'black-duck-report-recipients'),
        ('blackDuckScopes', 'black-duck-scopes')
    ]

    for (xml_prop, yaml_prop) in optional_str_props:
        XML.SubElement(xml_parent, xml_prop).text = data.get(
            yaml_prop, '')

    common_bool_props = [
        # yaml property name, xml property name, default value
        ('deploy-artifacts', 'deployArtifacts', True),
        ('discard-old-builds', 'discardOldBuilds', False),
        ('discard-build-artifacts', 'discardBuildArtifacts', False),
        ('publish-build-info', 'deployBuildInfo', False),
        ('env-vars-include', 'includeEnvVars', False),
        ('run-checks', 'runChecks', False),
        ('include-publish-artifacts', 'includePublishArtifacts', False),
        ('license-auto-discovery', 'licenseAutoDiscovery', True),
        ('enable-issue-tracker-integration', 'enableIssueTrackerIntegration',
            False),
        ('aggregate-build-issues', 'aggregateBuildIssues', False),
        ('black-duck-run-checks', 'blackDuckRunChecks', False),
        ('black-duck-include-published-artifacts',
            'blackDuckIncludePublishedArtifacts', False),
        ('auto-create-missing-component-requests',
            'autoCreateMissingComponentRequests', True),
        ('auto-discard-stale-component-requests',
            'autoDiscardStaleComponentRequests', True),
        ('filter-excluded-artifacts-from-build',
            'filterExcludedArtifactsFromBuild', False)
    ]
    convert_mapping_to_xml(
        xml_parent, data, common_bool_props, fail_required=True)

    if 'wrappers' in target:
        wrapper_bool_props = [
            ('enable-resolve-artifacts', 'enableResolveArtifacts', False),
            ('disable-license-auto-discovery',
                'disableLicenseAutoDiscovery', False),
            ('record-all-dependencies',
                'recordAllDependencies', False)
        ]
        convert_mapping_to_xml(
            xml_parent, data, wrapper_bool_props, fail_required=True)

    if 'publishers' in target:
        publisher_bool_props = [
            ('even-if-unstable', 'evenIfUnstable', False),
            ('pass-identified-downstream', 'passIdentifiedDownstream', False),
            ('allow-promotion-of-non-staged-builds',
                'allowPromotionOfNonStagedBuilds', False)
        ]
        convert_mapping_to_xml(
            xml_parent, data, publisher_bool_props, fail_required=True)


def artifactory_common_details(details, data):
    XML.SubElement(details, 'artifactoryName').text = data.get('name', '')
    XML.SubElement(details, 'artifactoryUrl').text = data.get('url', '')


def artifactory_repository(xml_parent, data, target):
    if 'release' in target:
        XML.SubElement(xml_parent, 'keyFromText').text = data.get(
            'deploy-release-repo-key', '')
        XML.SubElement(xml_parent, 'keyFromSelect').text = data.get(
            'deploy-release-repo-key', '')
        XML.SubElement(xml_parent, 'dynamicMode').text = str(
            data.get('deploy-dynamic-mode', False)).lower()

    if 'snapshot' in target:
        XML.SubElement(xml_parent, 'keyFromText').text = data.get(
            'deploy-snapshot-repo-key', '')
        XML.SubElement(xml_parent, 'keyFromSelect').text = data.get(
            'deploy-snapshot-repo-key', '')
        XML.SubElement(xml_parent, 'dynamicMode').text = str(
            data.get('deploy-dynamic-mode', False)).lower()


def append_git_revision_config(parent, config_def):
    params = XML.SubElement(
        parent, 'hudson.plugins.git.GitRevisionBuildParameters')

    try:
        # If git-revision is a boolean, the get() will
        # throw an AttributeError
        combine_commits = str(
            config_def.get('combine-queued-commits', False)).lower()
    except AttributeError:
        combine_commits = 'false'

    XML.SubElement(params, 'combineQueuedCommits').text = combine_commits


def test_fairy_common(xml_element, data):
    xml_element.set('plugin', 'TestFairy')
    valid_max_duration = ['10m', '60m', '300m', '1440m']
    valid_interval = [1, 2, 5]
    valid_video_quality = ['high', 'medium', 'low']

    mappings = [
        # General
        ('apikey', 'apiKey', None),
        ('appfile', 'appFile', None),
        ('tester-groups', 'testersGroups', ''),
        ('notify-testers', 'notifyTesters', True),
        ('autoupdate', 'autoUpdate', True),
        # Session
        ('max-duration', 'maxDuration', '10m', valid_max_duration),
        ('record-on-background', 'recordOnBackground', False),
        ('data-only-wifi', 'dataOnlyWifi', False),
        # Video
        ('video-enabled', 'isVideoEnabled', True),
        ('screenshot-interval', 'screenshotInterval', 1, valid_interval),
        ('video-quality', 'videoQuality', 'high', valid_video_quality),
        # Metrics
        ('cpu', 'cpu', True),
        ('memory', 'memory', True),
        ('logs', 'logs', True),
        ('network', 'network', False),
        ('phone-signal', 'phoneSignal', False),
        ('wifi', 'wifi', False),
        ('gps', 'gps', False),
        ('battery', 'battery', False),
        ('opengl', 'openGl', False),
        # Advanced options
        ('advanced-options', 'advancedOptions', '')
    ]
    convert_mapping_to_xml(xml_element, data, mappings, fail_required=True)


def convert_mapping_to_xml(parent, data, mapping, fail_required=False):
    """Convert mapping to XML

    fail_required affects the last parameter of the mapping field when it's
    parameter is set to 'None'. When fail_required is True then a 'None' value
    represents a required configuration so will raise a MissingAttributeError
    if the user does not provide the configuration.

    If fail_required is False parameter is treated as optional. Logic will skip
    configuring the XML tag for the parameter. We recommend for new plugins to
    set fail_required=True and instead of optional parameters provide a default
    value for all paramters that are not required instead.

    valid_options provides a way to check if the value the user input is from a
    list of available options. When the user pass a value that is not supported
    from the list, it raise an InvalidAttributeError.

    valid_dict provides a way to set options through their key and value. If
    the user input corresponds to a key, the XML tag will use the key's value
    for its element. When the user pass a value that there are no keys for,
    it raise an InvalidAttributeError.
    """
    for elem in mapping:
        (optname, xmlname, val) = elem[:3]
        val = data.get(optname, val)

        valid_options = []
        valid_dict = {}
        if len(elem) == 4:
            if type(elem[3]) is list:
                valid_options = elem[3]
            if type(elem[3]) is dict:
                valid_dict = elem[3]

        # Use fail_required setting to allow support for optional parameters
        # we will phase this out in the future as we rework plugins so that
        # optional parameters use a default setting instead.
        if val is None and fail_required is True:
            raise MissingAttributeError(optname)

        # (Deprecated) in the future we will default to fail_required True
        # if no value is provided then continue else leave it
        # up to the user if they want to use an empty XML tag
        if val is None and fail_required is False:
            continue

        if valid_dict:
            if val not in valid_dict:
                raise InvalidAttributeError(optname, val, valid_dict.keys())

        if valid_options:
            if val not in valid_options:
                raise InvalidAttributeError(optname, val, valid_options)

        if type(val) == bool:
            val = str(val).lower()

        if val in valid_dict:
            XML.SubElement(parent, xmlname).text = str(valid_dict[val])
        else:
            XML.SubElement(parent, xmlname).text = str(val)

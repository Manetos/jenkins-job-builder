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
The Parameters module allows you to specify build parameters for a job.

**Component**: parameters
  :Macro: parameter
  :Entry Point: jenkins_jobs.parameters

Example::

  job:
    name: test_job

    parameters:
      - string:
          name: FOO
          default: bar
          description: "A parameter named FOO, defaults to 'bar'."
"""

import xml.etree.ElementTree as XML

from jenkins_jobs.errors import JenkinsJobsException
from jenkins_jobs.errors import MissingAttributeError
from jenkins_jobs.errors import InvalidAttributeError
import jenkins_jobs.modules.base
from jenkins_jobs.modules.helpers import copyartifact_build_selector


def base_param(registry, xml_parent, data, do_default, ptype):
    pdef = XML.SubElement(xml_parent, ptype)
    XML.SubElement(pdef, 'name').text = data['name']
    XML.SubElement(pdef, 'description').text = data.get('description', '')
    if do_default:
        default = data.get('default', None)
        if default:
            XML.SubElement(pdef, 'defaultValue').text = default
        else:
            XML.SubElement(pdef, 'defaultValue')
    return pdef


def string_param(registry, xml_parent, data):
    """yaml: string
    A string parameter.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)

    Example::

      parameters:
        - string:
            name: FOO
            default: bar
            description: "A parameter named FOO, defaults to 'bar'."
    """
    base_param(registry, xml_parent, data, True,
               'hudson.model.StringParameterDefinition')


def promoted_param(registry, xml_parent, data):
    """yaml: promoted build
    A promoted build parameter.
    Requires the Jenkins :jenkins-wiki:`Promoted Builds Plugin
    <Promoted+Builds+Plugin>`.

    :arg str name: the name of the parameter (required)
    :arg str project-name: the job from which the user can pick runs (required)
    :arg str promotion-name: promotion process to choose from (optional)
    :arg str description: a description of the parameter (optional)

    Example:

    .. literalinclude::
        /../../tests/parameters/fixtures/promoted-build-param001.yaml
       :language: yaml

    """
    pdef = base_param(registry, xml_parent, data, False,
                      'hudson.plugins.promoted__builds.parameters.'
                      'PromotedBuildParameterDefinition')
    try:
        XML.SubElement(pdef, 'projectName').text = data['project-name']
    except KeyError:
        raise MissingAttributeError('project-name')

    XML.SubElement(pdef, 'promotionProcessName').text = data.get(
        'promotion-name', None)


def password_param(registry, xml_parent, data):
    """yaml: password
    A password parameter.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)

    Example::

      parameters:
        - password:
            name: FOO
            default: 1HSC0Ts6E161FysGf+e1xasgsHkgleLh09JUTYnipPvw=
            description: "A parameter named FOO."
    """
    base_param(registry, xml_parent, data, True,
               'hudson.model.PasswordParameterDefinition')


def bool_param(registry, xml_parent, data):
    """yaml: bool
    A boolean parameter.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)

    Example::

      parameters:
        - bool:
            name: FOO
            default: false
            description: "A parameter named FOO, defaults to 'false'."
    """
    data['default'] = str(data.get('default', False)).lower()
    base_param(registry, xml_parent, data, True,
               'hudson.model.BooleanParameterDefinition')


def file_param(registry, xml_parent, data):
    """yaml: file
    A file parameter.

    :arg str name: the target location for the file upload
    :arg str description: a description of the parameter (optional)

    Example::

      parameters:
        - file:
            name: test.txt
            description: "Upload test.txt."
    """
    base_param(registry, xml_parent, data, False,
               'hudson.model.FileParameterDefinition')


def text_param(registry, xml_parent, data):
    """yaml: text
    A text parameter.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)

    Example::

      parameters:
        - text:
            name: FOO
            default: bar
            description: "A parameter named FOO, defaults to 'bar'."
    """
    base_param(registry, xml_parent, data, True,
               'hudson.model.TextParameterDefinition')


def label_param(registry, xml_parent, data):
    """yaml: label
    A node label parameter.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)

    Example::

      parameters:
        - label:
            name: node
            default: precise
            description: "The node on which to run the job"
    """
    base_param(registry, xml_parent, data, True,
               'org.jvnet.jenkins.plugins.nodelabelparameter.'
               'LabelParameterDefinition')


def node_param(registry, xml_parent, data):
    """yaml: node
    Defines a list of nodes where this job could potentially be executed on.
    Restrict where this project can be run, If your using a node or label
    parameter to run your job on a particular node, you should not use the
    option "Restrict where this project can be run" in the job configuration
    - it will not have any effect to the selection of your node anymore!

    :arg str name: the name of the parameter
    :arg str description: a description of the parameter (optional)
    :arg list default-slaves: The nodes used when job gets triggered
        by anything else other than manually
    :arg list allowed-slaves: The nodes available for selection
        when job gets triggered manually. Empty means 'All'.
    :arg bool ignore-offline-nodes: Ignore nodes not online or not having
        executors (default false)
    :arg bool allowed-multiselect: Allow multi node selection for concurrent
        builds - this option only makes sense (and must be selected!) in
        case the job is configured with: "Execute concurrent builds if
        necessary". With this configuration the build will be executed on all
        the selected nodes in parallel. (default false)

    Example:

    .. literalinclude::  /../../tests/parameters/fixtures/node-param001.yaml
       :language: yaml

    """
    pdef = base_param(registry, xml_parent, data, False,
                      'org.jvnet.jenkins.plugins.nodelabelparameter.'
                      'NodeParameterDefinition')
    default = XML.SubElement(pdef, 'defaultSlaves')
    if 'default-slaves' in data:
        for slave in data['default-slaves']:
            XML.SubElement(default, 'string').text = slave
    allowed = XML.SubElement(pdef, 'allowedSlaves')
    if 'allowed-slaves' in data:
        for slave in data['allowed-slaves']:
            XML.SubElement(allowed, 'string').text = slave
    XML.SubElement(pdef, 'ignoreOfflineNodes').text = str(
        data.get('ignore-offline-nodes', False)).lower()

    if data.get('allowed-multiselect', False):
        XML.SubElement(pdef, 'triggerIfResult').text = \
            'allowMultiSelectionForConcurrentBuilds'
    else:
        XML.SubElement(pdef, 'triggerIfResult').text = \
            'multiSelectionDisallowed'
    XML.SubElement(pdef, 'allowMultiNodeSelection').text = str(
        data.get('allowed-multiselect', False)).lower()
    XML.SubElement(pdef, 'triggerConcurrentBuilds').text = str(
        data.get('allowed-multiselect', False)).lower()


def choice_param(registry, xml_parent, data):
    """yaml: choice
    A single selection parameter.

    :arg str name: the name of the parameter
    :arg list choices: the available choices
    :arg str description: a description of the parameter (optional)

    Example::

      parameters:
        - choice:
            name: project
            choices:
              - nova
              - glance
            description: "On which project to run?"
    """
    pdef = base_param(registry, xml_parent, data, False,
                      'hudson.model.ChoiceParameterDefinition')
    choices = XML.SubElement(pdef, 'choices',
                             {'class': 'java.util.Arrays$ArrayList'})
    a = XML.SubElement(choices, 'a', {'class': 'string-array'})
    for choice in data['choices']:
        XML.SubElement(a, 'string').text = choice


def run_param(registry, xml_parent, data):
    """yaml: run
    A run parameter.

    :arg str name: the name of the parameter
    :arg str project-name: the name of job from which the user can pick runs
    :arg str description: a description of the parameter (optional)

    Example:

    .. literalinclude::  /../../tests/parameters/fixtures/run-param001.yaml
       :language: yaml

    """
    pdef = base_param(registry, xml_parent, data, False,
                      'hudson.model.RunParameterDefinition')
    XML.SubElement(pdef, 'projectName').text = data['project-name']


def extended_choice_param(registry, xml_parent, data):
    """yaml: extended-choice
    Creates an extended choice parameter where values can be read from a file
    Requires the Jenkins :jenkins-wiki:`Extended Choice Parameter Plugin
    <Extended+Choice+Parameter+plugin>`.

    :arg str name: name of the parameter
    :arg str description: description of the parameter
        (optional, default '')
    :arg str property-file: location of property file to read from
        (optional, default '')
    :arg str property-key: key for the property-file (optional, default '')
    :arg bool quote-value: whether to put quotes around the property
        when passing to Jenkins (optional, default false)
    :arg str visible-items: number of items to show in the list
        (optional, default 5)
    :arg str type: type of select, can be single-select, multi-select,
        radio, checkbox or textbox (optional, default single-select)
    :arg str value: comma separated list of values for the single select
        or multi-select box (optional, default '')
    :arg str default-value: used to set the initial selection of the
        single-select or multi-select box (optional, default '')
    :arg str value-description: comma separated list of value descriptions
        for the single select or multi-select box (optional, default '')
    :arg str default-property-file: location of property file when default
        value needs to come from a property file (optional, default '')
    :arg str default-property-key: key for the default property file
        (optional, default '')
    :arg str description-property-file: location of property file when value
        description needs to come from a property file (optional, default '')
    :arg str description-property-key: key for the value description
        property file (optional, default '')
    :arg str multi-select-delimiter: value between selections when the
        parameter is a multi-select (optiona, default ',')

    Example:

    .. literalinclude:: \
    /../../tests/parameters/fixtures/extended-choice-param001.yaml
       :language: yaml

    """
    pdef = base_param(registry, xml_parent, data, False,
                      'com.cwctravel.hudson.plugins.'
                      'extended__choice__parameter.'
                      'ExtendedChoiceParameterDefinition')
    XML.SubElement(pdef, 'value').text = data.get('value', '')
    XML.SubElement(pdef, 'visibleItemCount').text = str(data.get(
        'visible-items', data.get('visible-item-count', 5)))
    XML.SubElement(pdef, 'multiSelectDelimiter').text = data.get(
        'multi-select-delimiter', ',')
    XML.SubElement(pdef, 'quoteValue').text = str(data.get('quote-value',
                                                  False)).lower()
    XML.SubElement(pdef, 'defaultValue').text = data.get(
        'default-value', '')
    XML.SubElement(pdef, 'descriptionPropertyValue').text = data.get(
        'value-description', '')
    choice = data.get('type', 'single-select')
    choicedict = {'single-select': 'PT_SINGLE_SELECT',
                  'multi-select': 'PT_MULTI_SELECT',
                  'radio': 'PT_RADIO',
                  'checkbox': 'PT_CHECKBOX',
                  'textbox': 'PT_TEXTBOX',
                  'PT_SINGLE_SELECT': 'PT_SINGLE_SELECT',
                  'PT_MULTI_SELECT': 'PT_MULTI_SELECT',
                  'PT_RADIO': 'PT_RADIO',
                  'PT_CHECKBOX': 'PT_CHECKBOX',
                  'PT_TEXTBOX': 'PT_TEXTBOX'}

    if choice in choicedict:
        XML.SubElement(pdef, 'type').text = choicedict[choice]
    else:
        raise JenkinsJobsException("Type entered is not valid, must be one "
                                   "of: single-select, multi-select, radio, "
                                   "textbox or checkbox")
    XML.SubElement(pdef, 'propertyFile').text = data.get('property-file', '')
    XML.SubElement(pdef, 'propertyKey').text = data.get('property-key', '')
    XML.SubElement(pdef, 'defaultPropertyFile').text = data.get(
        'default-property-file', '')
    XML.SubElement(pdef, 'defaultPropertyKey').text = data.get(
        'default-property-key', '')
    XML.SubElement(pdef, 'descriptionPropertyFile').text = data.get(
        'description-property-file', '')
    XML.SubElement(pdef, 'descriptionPropertyKey').text = data.get(
        'description-property-key', '')


def validating_string_param(registry, xml_parent, data):
    """yaml: validating-string
    A validating string parameter
    Requires the Jenkins :jenkins-wiki:`Validating String Plugin
    <Validating+String+Parameter+Plugin>`.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)
    :arg str regex: a regular expression to validate the string
    :arg str msg: a message to display upon failed validation

    Example::

      parameters:
        - validating-string:
            name: FOO
            default: bar
            description: "A parameter named FOO, defaults to 'bar'."
            regex: [A-Za-z]*
            msg: Your entered value failed validation
    """
    pdef = base_param(registry, xml_parent, data, True,
                      'hudson.plugins.validating__string__parameter.'
                      'ValidatingStringParameterDefinition')
    XML.SubElement(pdef, 'regex').text = data['regex']
    XML.SubElement(pdef, 'failedValidationMessage').text = data['msg']


def svn_tags_param(registry, xml_parent, data):
    """yaml: svn-tags
    A svn tag parameter
    Requires the Jenkins :jenkins-wiki:`Parameterized Trigger Plugin
    <Parameterized+Trigger+Plugin>`.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)
    :arg str url: the url to list tags from
    :arg str filter: the regular expression to filter tags

    Example::

      parameters:
        - svn-tags:
            name: BRANCH_NAME
            default: release
            description: A parameter named BRANCH_NAME default is release
            url: http://svn.example.com/repo
            filter: [A-za-z0-9]*
    """
    pdef = base_param(registry, xml_parent, data, True,
                      'hudson.scm.listtagsparameter.'
                      'ListSubversionTagsParameterDefinition')
    XML.SubElement(pdef, 'tagsDir').text = data['url']
    XML.SubElement(pdef, 'tagsFilter').text = data.get('filter', None)
    XML.SubElement(pdef, 'reverseByDate').text = "true"
    XML.SubElement(pdef, 'reverseByName').text = "false"
    XML.SubElement(pdef, 'maxTags').text = "100"
    XML.SubElement(pdef, 'uuid').text = "1-1-1-1-1"


def dynamic_choice_param(registry, xml_parent, data):
    """yaml: dynamic-choice
    Dynamic Choice Parameter
    Requires the Jenkins :jenkins-wiki:`Jenkins Dynamic Parameter Plug-in
    <Dynamic+Parameter+Plug-in>`.

    :arg str name: the name of the parameter
    :arg str description: a description of the parameter (optional)
    :arg str script: Groovy expression which generates the potential choices.
    :arg bool remote: the script will be executed on the slave where the build
        is started (default false)
    :arg str classpath: class path for script (optional)
    :arg bool read-only: user can't modify parameter once populated
        (default false)

    Example::

      parameters:
        - dynamic-choice:
            name: OPTIONS
            description: "Available options"
            script: "['optionA', 'optionB']"
            remote: false
            read-only: false
    """
    dynamic_param_common(registry, xml_parent, data,
                         'ChoiceParameterDefinition')


def dynamic_string_param(registry, xml_parent, data):
    """yaml: dynamic-string
    Dynamic Parameter
    Requires the Jenkins :jenkins-wiki:`Jenkins Dynamic Parameter Plug-in
    <Dynamic+Parameter+Plug-in>`.

    :arg str name: the name of the parameter
    :arg str description: a description of the parameter (optional)
    :arg str script: Groovy expression which generates the potential choices
    :arg bool remote: the script will be executed on the slave where the build
        is started (default false)
    :arg str classpath: class path for script (optional)
    :arg bool read-only: user can't modify parameter once populated
        (default false)

    Example::

      parameters:
        - dynamic-string:
            name: FOO
            description: "A parameter named FOO, defaults to 'bar'."
            script: "bar"
            remote: false
            read-only: false
    """
    dynamic_param_common(registry, xml_parent, data,
                         'StringParameterDefinition')


def dynamic_choice_scriptler_param(registry, xml_parent, data):
    """yaml: dynamic-choice-scriptler
    Dynamic Choice Parameter (Scriptler)
    Requires the Jenkins :jenkins-wiki:`Jenkins Dynamic Parameter Plug-in
    <Dynamic+Parameter+Plug-in>`.

    :arg str name: the name of the parameter
    :arg str description: a description of the parameter (optional)
    :arg str script-id: Groovy script which generates the default value
    :arg list parameters: parameters to corresponding script

        :Parameter: * **name** (`str`) Parameter name
                    * **value** (`str`) Parameter value
    :arg bool remote: the script will be executed on the slave where the build
        is started (default false)
    :arg bool read-only: user can't modify parameter once populated
        (default false)

    Example::

      parameters:
        - dynamic-choice-scriptler:
            name: OPTIONS
            description: "Available options"
            script-id: "scriptid.groovy"
            parameters:
              - name: param1
                value: value1
              - name: param2
                value: value2
            remote: false
            read-only: false
    """
    dynamic_scriptler_param_common(registry, xml_parent, data,
                                   'ScriptlerChoiceParameterDefinition')


def dynamic_string_scriptler_param(registry, xml_parent, data):
    """yaml: dynamic-string-scriptler
    Dynamic Parameter (Scriptler)
    Requires the Jenkins :jenkins-wiki:`Jenkins Dynamic Parameter Plug-in
    <Dynamic+Parameter+Plug-in>`.

    :arg str name: the name of the parameter
    :arg str description: a description of the parameter (optional)
    :arg str script-id: Groovy script which generates the default value
    :arg list parameters: parameters to corresponding script

        :Parameter: * **name** (`str`) Parameter name
                    * **value** (`str`) Parameter value
    :arg bool remote: the script will be executed on the slave where the build
        is started (default false)
    :arg bool read-only: user can't modify parameter once populated
        (default false)

    Example::

      parameters:
        - dynamic-string-scriptler:
            name: FOO
            description: "A parameter named FOO, defaults to 'bar'."
            script-id: "scriptid.groovy"
            parameters:
              - name: param1
                value: value1
              - name: param2
                value: value2
            remote: false
            read-only: false
    """
    dynamic_scriptler_param_common(registry, xml_parent, data,
                                   'ScriptlerStringParameterDefinition')


def dynamic_param_common(registry, xml_parent, data, ptype):
    pdef = base_param(registry, xml_parent, data, False,
                      'com.seitenbau.jenkins.plugins.dynamicparameter.'
                      + ptype)
    XML.SubElement(pdef, '__remote').text = str(
        data.get('remote', False)).lower()
    XML.SubElement(pdef, '__script').text = data.get('script', None)
    localBaseDir = XML.SubElement(pdef, '__localBaseDirectory',
                                  {'serialization': 'custom'})
    filePath = XML.SubElement(localBaseDir, 'hudson.FilePath')
    default = XML.SubElement(filePath, 'default')
    XML.SubElement(filePath, 'boolean').text = "true"
    XML.SubElement(default, 'remote').text = \
        "/var/lib/jenkins/dynamic_parameter/classpath"
    XML.SubElement(pdef, '__remoteBaseDirectory').text = \
        "dynamic_parameter_classpath"
    XML.SubElement(pdef, '__classPath').text = data.get('classpath', None)
    XML.SubElement(pdef, 'readonlyInputField').text = str(
        data.get('read-only', False)).lower()


def dynamic_scriptler_param_common(registry, xml_parent, data, ptype):
    pdef = base_param(registry, xml_parent, data, False,
                      'com.seitenbau.jenkins.plugins.dynamicparameter.'
                      'scriptler.' + ptype)
    XML.SubElement(pdef, '__remote').text = str(
        data.get('remote', False)).lower()
    XML.SubElement(pdef, '__scriptlerScriptId').text = data.get(
        'script-id', None)
    parametersXML = XML.SubElement(pdef, '__parameters')
    parameters = data.get('parameters', [])
    if parameters:
        for parameter in parameters:
            parameterXML = XML.SubElement(parametersXML,
                                          'com.seitenbau.jenkins.plugins.'
                                          'dynamicparameter.scriptler.'
                                          'ScriptlerParameterDefinition_'
                                          '-ScriptParameter')
            XML.SubElement(parameterXML, 'name').text = parameter['name']
            XML.SubElement(parameterXML, 'value').text = parameter['value']
    XML.SubElement(pdef, 'readonlyInputField').text = str(data.get(
        'read-only', False)).lower()


def matrix_combinations_param(registry, xml_parent, data):
    """yaml: matrix-combinations
    Matrix combinations parameter
    Requires the Jenkins :jenkins-wiki:`Matrix Combinations Plugin
    <Matrix+Combinations+Plugin>`.

    :arg str name: the name of the parameter
    :arg str description: a description of the parameter (optional)
    :arg str filter: Groovy expression to use filter the combination by
        default (optional)

    Example:

    .. literalinclude:: \
    /../../tests/parameters/fixtures/matrix-combinations-param001.yaml
       :language: yaml

    """
    element_name = 'hudson.plugins.matrix__configuration__parameter.' \
                   'MatrixCombinationsParameterDefinition'
    pdef = XML.SubElement(xml_parent, element_name)
    if 'name' not in data:
        raise JenkinsJobsException('matrix-combinations must have a name '
                                   'parameter.')
    XML.SubElement(pdef, 'name').text = data['name']
    XML.SubElement(pdef, 'description').text = data.get('description', '')
    combination_filter = data.get('filter')
    if combination_filter:
        XML.SubElement(pdef, 'defaultCombinationFilter').text = \
            combination_filter

    return pdef


def copyartifact_build_selector_param(registry, xml_parent, data):
    """yaml: copyartifact-build-selector

    Control via a build parameter, which build the copyartifact plugin should
    copy when it is configured to use 'build-param'. Requires the Jenkins
    :jenkins-wiki:`Copy Artifact plugin <Copy+Artifact+Plugin>`.

    :arg str name: name of the build parameter to store the selection in
    :arg str description: a description of the parameter (optional)
    :arg str which-build: which to provide as the default value in the UI. See
        ``which-build`` param of :py:mod:`~builders.copyartifact` from the
        builders module for the available values as well as options available
        that control additional behaviour for the selected value.

    Example:

    .. literalinclude::
        /../../tests/parameters/fixtures/copyartifact-build-selector001.yaml
       :language: yaml

    """

    t = XML.SubElement(xml_parent, 'hudson.plugins.copyartifact.'
                       'BuildSelectorParameter')
    try:
        name = data['name']
    except KeyError:
        raise MissingAttributeError('name')

    XML.SubElement(t, 'name').text = name
    XML.SubElement(t, 'description').text = data.get('description', '')

    copyartifact_build_selector(t, data, 'defaultSelector')


def maven_metadata_param(registry, xml_parent, data):
    """yaml: maven-metadata
    This parameter allows the resolution of maven artifact versions
    by contacting the repository and reading the maven-metadata.xml.
    Requires the Jenkins :jenkins-wiki:`Maven Metadata Plugin
    <Maven+Metadata+Plugin>`.

    :arg str name: Name of the parameter
    :arg str description: Description of the parameter (optional)
    :arg str repository-base-url: URL from where you retrieve your artifacts
        (default '')
    :arg str repository-username: Repository's username if authentication is
        required. (default '')
    :arg str repository-password: Repository's password if authentication is
        required. (default '')
    :arg str artifact-group-id: Unique project identifier (default '')
    :arg str artifact-id: Name of the artifact without version (default '')
    :arg str packaging: Artifact packaging option. Could be something such as
        jar, zip, pom.... (default '')
    :arg str versions-filter: Specify a regular expression which will be used
        to filter the versions which are actually displayed when triggering a
        new build. (default '')
    :arg str default-value: For features such as SVN polling a default value
        is required. If job will only be started manually, this field is not
        necessary. (default '')
    :arg str maximum-versions-to-display: The maximum number of versions to
        display in the drop-down. Any non-number value as well as 0 or negative
        values will default to all. (default 10)
    :arg str sorting-order: ascending or descending
        (default descending)

    Example:

    .. literalinclude::
       /../../tests/parameters/fixtures/maven-metadata-param001.yaml
       :language: yaml

    """
    pdef = base_param(registry, xml_parent, data, False,
                      'eu.markov.jenkins.plugin.mvnmeta.'
                      'MavenMetadataParameterDefinition')
    XML.SubElement(pdef, 'repoBaseUrl').text = data.get('repository-base-url',
                                                        '')
    XML.SubElement(pdef, 'groupId').text = data.get('artifact-group-id', '')
    XML.SubElement(pdef, 'artifactId').text = data.get('artifact-id', '')
    XML.SubElement(pdef, 'packaging').text = data.get('packaging', '')
    XML.SubElement(pdef, 'defaultValue').text = data.get('default-value', '')
    XML.SubElement(pdef, 'versionFilter').text = data.get('versions-filter',
                                                          '')

    sort_order = data.get('sorting-order', 'descending').lower()
    sort_dict = {'descending': 'DESC',
                 'ascending': 'ASC'}

    if sort_order not in sort_dict:
        raise InvalidAttributeError(sort_order, sort_order, sort_dict.keys())

    XML.SubElement(pdef, 'sortOrder').text = sort_dict[sort_order]
    XML.SubElement(pdef, 'maxVersions').text = str(data.get(
        'maximum-versions-to-display', 10))
    XML.SubElement(pdef, 'username').text = data.get('repository-username', '')
    XML.SubElement(pdef, 'password').text = data.get('repository-password', '')


def hidden_param(parser, xml_parent, data):
    """yaml: hidden
    Allows you to use parameters hidden from the build with parameter page.
    Requires the Jenkins :jenkins-wiki:`Hidden Parameter Plugin
    <Hidden+Parameter+Plugin>`.

    :arg str name: the name of the parameter
    :arg str default: the default value of the parameter (optional)
    :arg str description: a description of the parameter (optional)

    Example:

    .. literalinclude::
       /../../tests/parameters/fixtures/hidden-param001.yaml
       :language: yaml

    """
    base_param(parser, xml_parent, data, True,
               'com.wangyin.parameter.WHideParameterDefinition')


def random_string_param(registry, xml_parent, data):
    """yaml: random-string
    This parameter generates a random string and passes it to the
    build, preventing Jenkins from combining queued builds.
    Requires the Jenkins :jenkins-wiki:`Random String Parameter Plugin
    <Random+String+Parameter+Plugin>`.

    :arg str name: Name of the parameter
    :arg str description: Description of the parameter (default '')
    :arg str failed-validation-message: Failure message to display for invalid
        input (default '')

    Example:

    .. literalinclude::
       /../../tests/parameters/fixtures/random-string-param001.yaml
       :language: yaml
    """
    pdef = XML.SubElement(xml_parent,
                          'hudson.plugins.random__string__parameter.'
                          'RandomStringParameterDefinition')
    if 'name' not in data:
        raise JenkinsJobsException('random-string must have a name parameter.')
    XML.SubElement(pdef, 'name').text = data['name']
    XML.SubElement(pdef, 'description').text = data.get('description', '')
    XML.SubElement(pdef, 'failedValidationMessage').text = data.get(
        'failed-validation-message', '')


class Parameters(jenkins_jobs.modules.base.Base):
    sequence = 21

    component_type = 'parameter'
    component_list_type = 'parameters'

    def gen_xml(self, xml_parent, data):
        properties = xml_parent.find('properties')
        if properties is None:
            properties = XML.SubElement(xml_parent, 'properties')

        parameters = data.get('parameters', [])
        hmodel = 'hudson.model.'
        if parameters:
            # The conditionals here are to work around the extended_choice
            # parameter also being definable in the properties module.  This
            # usage has been deprecated but not removed.  Because it may have
            # added these elements before us, we need to check if they already
            # exist, and only add them if they're missing.
            pdefp = properties.find(hmodel + 'ParametersDefinitionProperty')
            if pdefp is None:
                pdefp = XML.SubElement(properties,
                                       hmodel + 'ParametersDefinitionProperty')
            pdefs = pdefp.find('parameterDefinitions')
            if pdefs is None:
                pdefs = XML.SubElement(pdefp, 'parameterDefinitions')
            for param in parameters:
                self.registry.dispatch('parameter', pdefs, param)

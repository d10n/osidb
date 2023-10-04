import random

import pytest
from django.utils import timezone

from apps.osim.models import Check, State, Workflow
from apps.osim.workflow import WorkflowFramework, WorkflowModel
from osidb.models import Flaw, FlawMeta, FlawSource, FlawType, Impact
from osidb.tests.factories import (
    AffectFactory,
    FlawCVSSFactory,
    FlawFactory,
    FlawMetaFactory,
    PackageFactory,
)

pytestmark = pytest.mark.unit


def assert_state_equals(current, expected):
    message = f'flaw classified as {current.name}, expected {expected["name"]}'
    assert current.name == expected["name"], message


class CheckDescFactory:
    """
    test factory to produce random check descriptions together
    with flaw properties according to the specified conditions
    """

    # TODO embargoed is not model attribute any more but annotation
    # so the embargo related checks currently error out and we need to accout for the change
    PROPERTY_TRUE = [
        ("major_incident", "is_major_incident", True),
        # ("embargoed", "embargoed", True),
    ]
    NOT_PROPERTY_TRUE = [
        ("not major incident", "is_major_incident", False),
        # ("not embargoed", "embargoed", False),
    ]
    HAS_PROPERTY_TRUE = [
        ("has uuid", "uuid", "35d1ad45-0dba-41a3-bad6-5dd36d624ead"),
        ("has cve", "cve_id", "CVE-2020-1234"),
        ("has type", "type", FlawType.VULNERABILITY),
        ("has created_dt", "created_dt", timezone.now()),
        ("has updated_dt", "updated_dt", timezone.now()),
        ("has impact", "impact", Impact.MODERATE),
        ("has title", "title", "random title"),
        ("has description", "description", "random description"),
        ("has summary", "summary", "random summary"),
        ("has statement", "statement", "random statement"),
        ("has cwe", "cwe_id", "CWE-123"),
        ("has unembargo_dt", "unembargo_dt", timezone.now()),
        ("has source", "source", FlawSource.APPLE),
        ("has reported_dt", "reported_dt", timezone.now()),
        ("has cvss2", "cvss2", "5.2/AV:L/AC:H/Au:N/C:P/I:P/A:C"),
        ("has cvss2_score", "cvss2_score", "5.2"),
        ("has cvss3", "cvss3", "6.2/CVSS:3.0/AV:L/AC:H/PR:N/UI:N/S:U/C:L/I:L/A:H"),
        ("has cvss3_score", "cvss3_score", "6.2"),
        ("has is_major_incident", "is_major_incident", False),
    ]
    PROPERTY_FALSE = [
        ("major_incident", "is_major_incident", False),
        # ("embargoed", "embargoed", False),
    ]
    NOT_PROPERTY_FALSE = [
        ("not major incident", "is_major_incident", True),
        # ("not embargoed", "embargoed", True),
    ]
    HAS_PROPERTY_FALSE = [
        ("has summary", "summary", ""),
        ("has statement", "statement", ""),
        ("has cwe", "cwe_id", ""),
        ("has source", "source", ""),
        # ("has reported_dt", "reported_dt", None),
        ("has cvss2", "cvss2", ""),
        ("has cvss2_score", "cvss2_score", None),
        ("has cvss3", "cvss3", ""),
        ("has cvss3_score", "cvss3_score", None),
    ]

    ACCEPTS = {
        "property": PROPERTY_TRUE,
        "not_property": NOT_PROPERTY_TRUE,
        "has_property": HAS_PROPERTY_TRUE,
    }
    REJECTS = {
        "property": PROPERTY_FALSE,
        "not_property": NOT_PROPERTY_FALSE,
        "has_property": HAS_PROPERTY_FALSE,
    }

    @classmethod
    def _merge_dicts(cls, left, right):
        properties = left.copy()
        properties.update(right)
        return properties

    @classmethod
    def _get_universe(cls, accepts=None):
        universe = []

        if accepts is True or accepts is None:
            universe.append(cls.ACCEPTS)
        if accepts is False or accepts is None:
            universe.append(cls.REJECTS)

        return universe

    @classmethod
    def _get_pool(cls, cathegory=None, accepts=None, count=None, exclude=None):
        pool = []
        for domain in cls._get_universe(accepts):
            for domain_cathegory, space in domain.items():
                if cathegory == domain_cathegory or cathegory is None:
                    pool.extend(space)

        return cls._filter_pool(pool, count, exclude)

    @classmethod
    def _filter_pool(cls, pool, count=None, exclude=None):
        # we need to exclude flaw property and not just requirement
        # as some requirements share the flaw properties which could create conflict
        pool = pool if exclude is None else [r for r in pool if r[1] not in exclude]

        count = len(pool) if count is None else count
        count = (
            len(pool) if count > len(pool) else count
        )  # we may run out of possible checks
        return pool if count is None else random.sample(pool, count)

    @classmethod
    def generate(cls, cathegory=None, accepts=None, count=None, exclude=None):
        """
        generates requirements array and flaw properties dictionary based on the set criteria
            - the behavior with unexpected paramenter values is undefined
            - the result length may be less than count if conflicting properties were filtered out
        """
        requirements = []
        flaw_properties = {}
        for requirement, flaw_property, value in cls._get_pool(
            cathegory, accepts, count, exclude
        ):
            # skip conflicting properties
            if flaw_property in flaw_properties:
                continue
            requirements.append(requirement)
            flaw_properties[flaw_property] = value

        flaw_properties = cls._merge_dicts(
            flaw_properties, exclude if exclude is not None else {}
        )
        return requirements, flaw_properties


class StateFactory:
    """
    test factory to produce semi-random states based on set
    properties together with the corresponding flaw properties
    """

    index = 0

    def generate(self, accepts=None, count=0, exclude=None):
        """
        generates state array and flaw properties dictionary based on the set criteria
            - the behavior with unexpected paramenter values is undefined
        """
        states = []
        flaw_properties = {} if exclude is None else exclude

        for _ in range(count):
            requirements, flaw_properties = CheckDescFactory.generate(
                accepts=accepts, count=random.randint(1, 3), exclude=flaw_properties
            )
            states.append(
                State(
                    {
                        "name": WorkflowModel.OSIMState.values[self.index],
                        "requirements": requirements,
                    }
                )
            )
            self.index += 1

        return states, flaw_properties


class TestCheck:
    @pytest.mark.parametrize(
        "field,factory",
        [
            ("affects", lambda flaw: AffectFactory(flaw=flaw)),
            ("cvss_scores", lambda flaw: FlawCVSSFactory(flaw=flaw)),
            ("package_versions", lambda flaw: PackageFactory(flaw=flaw)),
        ],
    )
    def test_relational_property(self, field, factory):
        """
        test that properties from a relationship with flaw reject
        an empty list and accept it while having at least one element
        """
        flaw = FlawFactory(source=FlawSource.CVE, embargoed=False)
        check = Check(f"has {field}")
        assert not check(
            flaw
        ), f'check for "{check.name}" should have failed, but passed.'

        factory(flaw)
        assert check(flaw), f'check for "{check.name}" failed.'

    @pytest.mark.parametrize(
        "field",
        [
            "cve_id",
            "cwe_id",
            "created_dt",
            "impact",
            "description",
            "title",
            "summary",
            "cvss3",
            "source",
        ],
    )
    def test_property_positive(self, field):
        """
        test that flaw containing requested properties passes in check
        """
        # most of properties are being auto generated as non-null by factory
        flaw = FlawFactory(cwe_id="CWE-1", summary="random summary")
        check = Check(f"has {field}")

        assert check(flaw), f'check for "{check.name}" failed.'

    @pytest.mark.parametrize(
        "field,novalue",
        [
            ("cve_id", ""),
            ("cwe_id", ""),
            ("created_dt", ""),
            ("impact", Impact.NOVALUE),
            ("description", ""),
            ("title", ""),
            ("summary", ""),
            ("cvss3", ""),
            ("source", ""),
        ],
    )
    def test_property_negative(self, field, novalue):
        """
        test that flaw only passes a a check if it not contains
        an excluded properties
        """
        flaw = FlawFactory()
        setattr(flaw, field, novalue)
        check = Check(f"not {field}")

        assert check(flaw), f'check for "{check.name}" failed.'

    @pytest.mark.parametrize(
        "field,alias",
        [
            ("cve_id", "cve"),
            ("cwe_id", "cwe"),
        ],
    )
    def test_property_alias(self, field, alias):
        """
        test that check can use aliases
        """
        flaw = FlawFactory()
        setattr(flaw, field, "any value")
        check = Check(f"has {alias}")
        assert check(flaw), f'check for "{check.name}" failed.'

        setattr(flaw, field, "")
        assert not check(
            flaw
        ), f'check for "{check.name}" should have failed, but passed.'


class TestState:
    def test_empty_requirements(self):
        """test that a state with empty requirements accepts any flaw"""
        state = State(
            {
                "name": "random name",
                "requirements": [],
            }
        )
        flaw = FlawFactory()  # random flaw
        assert state.accepts(flaw), "state with no requirements rejects a flaw"

    def test_requirements(self):
        """test that a state accepts a flaw which satisfies its requirements"""

        requirements = [
            "has cve_id",
            "has impact",
            "has cvss3",
            "not cwe",
            "not description",
            "not title",
        ]
        state = State(
            {
                "name": "random name",
                "requirements": requirements,
            }
        )
        flaw = FlawFactory()
        # fields set outside factory to skip validation
        flaw.cwe_id = ""
        flaw.description = ""
        flaw.title = ""

        assert state.accepts(
            flaw
        ), f'flaw doesn\'t met the requirements "{requirements}"'

        flaw.cwe_id = "CWE-1"
        assert not state.accepts(
            flaw
        ), f'state accepted flaw without the requirements "{requirements}"'

        flaw.cwe_id = ""
        flaw.impact = Impact.NOVALUE
        assert not state.accepts(
            flaw
        ), f'state accepted flaw without the requirements "{requirements}"'


class TestWorkflow:
    def test_empty_conditions(self):
        """test that a workflow with empty conditions accepts any flaw"""
        workflow = Workflow(
            {
                "name": "random name",
                "description": "random description",
                "priority": 0,
                "conditions": [],
                "states": [],  # this is not valid but OK for this test
            }
        )
        flaw = FlawFactory()  # random flaw
        assert workflow.accepts(flaw), "workflow with no conditions rejects a flaw"

    @pytest.mark.parametrize(
        "conditions",
        [
            ["has description"],
            ["has description", "has title"],
            ["not description"],
            ["not description", "not title"],
            ["has description", "not title"],
        ],
    )
    def test_satisfied_conditions(self, conditions):
        """test that a workflow accepts a flaw which satisfies its conditions"""

        workflow = Workflow(
            {
                "name": "random name",
                "description": "random description",
                "priority": 0,
                "conditions": conditions,
                "states": [],  # this is not valid but OK for this test
            }
        )
        flaw = FlawFactory()
        for condition in conditions:
            mode, attr = condition.split(" ", maxsplit=1)
            attr = attr.replace(" ", "_")
            if mode == "has":
                setattr(flaw, attr, "valid value")
            elif mode == "not":
                setattr(flaw, attr, "")

        assert workflow.accepts(
            flaw
        ), f'flaw was rejected by workflow conditions "{conditions}"'

    @pytest.mark.parametrize(
        "conditions",
        [
            ["has description"],
            ["has description", "has title"],
            ["not description"],
            ["not description", "not title"],
            ["has description", "not title"],
        ],
    )
    def test_unsatisfied_conditions(self, conditions):
        """test that a workflow accepts a flaw which satisfies its conditions"""

        workflow = Workflow(
            {
                "name": "random name",
                "description": "random description",
                "priority": 0,
                "conditions": conditions,
                "states": [],  # this is not valid but OK for this test
            }
        )
        flaw = FlawFactory()
        for condition in conditions:
            mode, attr = condition.split(" ", maxsplit=1)
            attr = attr.replace(" ", "_")
            if mode == "has":
                setattr(flaw, attr, "")
            elif mode == "not":
                setattr(flaw, attr, "invalid value in a 'not' condition")

        assert not workflow.accepts(
            flaw
        ), f'flaw was wrongly accepted by workflow conditions "{conditions}"'

        # conditions partially satisfied
        if len(conditions) > 1:
            mode, attr = conditions[0].split(" ", maxsplit=1)
            attr = attr.replace(" ", "_")

            if mode == "has":
                setattr(flaw, attr, "valid value")
            elif mode == "not":
                setattr(flaw, attr, "")
        assert not workflow.accepts(
            flaw
        ), f'flaw was wrongly accepted by workflow conditions "{conditions}"'

    def test_classify(self):
        """test that a flaw is correctly classified in the workflow states"""
        state_new = {
            "name": "new",
            "requirements": [],
        }
        state_first = {"name": "first state", "requirements": ["has description"]}
        state_second = {"name": "second state", "requirements": ["has title"]}

        workflow = Workflow(
            {
                "name": "test workflow",
                "description": "a three step workflow to test classification",
                "priority": 0,
                "conditions": [],
                "states": [state_new, state_first, state_second],
            }
        )
        flaw = Flaw()
        assert_state_equals(workflow.classify(flaw), state_new)

        flaw.description = "valid description"
        assert_state_equals(workflow.classify(flaw), state_first)

        flaw.title = "valid title"
        assert_state_equals(workflow.classify(flaw), state_second)

        # Test that a flaw with a later state requirements does not skip previous states without requirements
        bypass_flaw = Flaw()
        bypass_flaw.cwe_id = "CWE-1"
        assert_state_equals(workflow.classify(bypass_flaw), state_new)


class TestWorkflowFramework:
    @pytest.mark.parametrize("count", [0, 1, 2, 3, 4, 5])
    def test_classify_default_state(self, count):
        """
        test that a flaw is always classified in some workflow when the default workflow exists
        """
        random_states, _ = StateFactory().generate(count=random.randint(1, 3))
        random_states[0].requirements = []  # default state
        default_workflow = Workflow(
            {
                "name": "random name",
                "description": "random description",
                "priority": 0,
                "conditions": [],  # default workflow with empty conditions
                "states": [],  # this is not valid but OK for this test
            }
        )
        default_workflow.states = random_states
        workflow_framework = WorkflowFramework()
        workflow_framework.register_workflow(default_workflow)

        for index in range(count):
            state_factory = StateFactory()
            random_states, _ = state_factory.generate(count=random.randint(1, 3))
            random_states[0].requirements = []  # default state
            conditions, _ = CheckDescFactory.generate()
            workflow = Workflow(
                {
                    "name": f"random name {index}",
                    "description": "random description",
                    "priority": index + 1,
                    "conditions": conditions,  # random workflow conditions
                    "states": [],  # this is not valid but OK for this test
                }
            )
            workflow.states = random_states
            workflow_framework.register_workflow(workflow)

        flaw = FlawFactory()  # random flaw

        message = "flaw was not classified in any workflow despite the default workflow exists"
        assert workflow_framework.classify(flaw, state=False) is not None, message

    @pytest.mark.parametrize("count", [1, 2, 3, 4, 5])
    def test_classify_priority(self, count):
        """
        test that a flaw is always classified in the most prior accepting workflow
        """
        workflow_framework = WorkflowFramework()

        random_states, _ = StateFactory().generate(count=1)
        random_states[0].requirements = []  # default state

        for index in range(count):
            workflow = Workflow(
                {
                    "name": f"random name {index}",
                    "description": "random description",
                    "priority": index + 1,
                    "conditions": [],
                    "states": [],  # this is not valid but OK for this test
                }
            )
            workflow.states = random_states
            workflow_framework.register_workflow(workflow)

        flaw = FlawFactory()  # random flaw

        message = (
            "flaw was classified in workflow with priority "
            f"{workflow_framework.classify(flaw, state=False).priority} "
            f"despite the most prior accepting workflow has priority {count}"
        )
        assert workflow_framework.classify(flaw, state=False).priority == count, message

    @pytest.mark.parametrize(
        "workflows,workflow_name,state_name",
        [
            (
                [
                    ("default", 0, True, 1),
                ],
                "default",
                "DRAFT",
            ),
            (
                [
                    ("another", 1, True, 2),
                    ("default", 0, True, 1),
                ],
                "another",
                "NEW",
            ),
            (
                [
                    ("another", 1, False, 1),
                    ("default", 0, True, 3),
                ],
                "default",
                "ANALYSIS",
            ),
            (
                [
                    ("first", 2, False, 2),
                    ("another", 1, True, 1),
                    ("default", 0, True, 2),
                ],
                "another",
                "DRAFT",
            ),
            # TODO this test case occasionally generates so complex workflows
            # that we are running out of flaw properties which results in empty
            # state requirements so they accept flaw instead of rejecting
            # - enable again when we have more flaw properties or this is refactored
            # (
            #     [
            #         ("first", 3, False, 1),
            #         ("better", 2, False, 1),
            #         ("another", 1, True, 2),
            #         ("default", 0, True, 1),
            #     ],
            #     "another",
            #     "NEW",
            # ),
        ],
    )
    def test_classify_complete(self, workflows, workflow_name, state_name):
        """test flaw classification in both workflow and state"""
        workflow_framework = WorkflowFramework()

        flaw_properties = {
            "unembargo_dt": None,
            "embargoed": None,
            "cvss3": "3.7/CVSS:3.0/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:L/A:N",
            "title": "EMBARGOED CVE-2022-1234 kernel: some description",
        }

        for name, priority, accepting, accepting_states in workflows:
            workflow = Workflow(
                {
                    "name": name,
                    "description": "random description",
                    "priority": priority,
                    "conditions": [],
                    "states": [],  # this is not valid but OK for this test
                }
            )
            # create conditions
            requirements, flaw_properties = CheckDescFactory.generate(
                accepts=accepting, count=1, exclude=flaw_properties
            )
            workflow.conditions = [Check(check_dest) for check_dest in requirements]
            # create states with one additional rejecting
            state_factory = StateFactory()
            a_states, flaw_properties = state_factory.generate(
                accepts=True, count=accepting_states, exclude=flaw_properties
            )
            r_states, flaw_properties = state_factory.generate(
                accepts=False, count=1, exclude=flaw_properties
            )
            workflow.states = a_states + r_states
            # register workflow in the workflow framework
            workflow_framework.register_workflow(workflow)

        flaw = FlawFactory.build(**flaw_properties)

        if flaw.is_major_incident:
            flaw.save(raise_validation_error=False)
            AffectFactory(flaw=flaw)
            FlawMetaFactory(
                flaw=flaw,
                type=FlawMeta.FlawMetaType.REQUIRES_SUMMARY,
                meta_attr={"status": "-"},
            )
        flaw.save()

        classified_workflow, classified_state = workflow_framework.classify(flaw)
        message = (
            f"flaw was classified in workflow to {classified_workflow.name}:{classified_state.name}"
            f" but the expected classification was {workflow_name}:{state_name}"
        )
        assert (
            classified_workflow.name == workflow_name
            and classified_state.name == state_name
        ), message


class TestFlaw:
    def test_init(self):
        """test that flaw gets workflow:state assigned on creation"""
        flaw = Flaw()
        assert flaw.osim_workflow
        assert flaw.osim_state

    def test_classification(self):
        """test flaw classification property"""
        flaw = Flaw()

        # stored classification
        assert flaw.osim_workflow == flaw.classification["workflow"]
        assert flaw.osim_state == flaw.classification["state"]
        # computed classification
        old_computed_workflow = flaw.classify()["workflow"]
        old_computed_state = flaw.classify()["state"]
        assert flaw.osim_workflow == old_computed_workflow
        assert flaw.osim_state == old_computed_state

        # assing new and different classification
        for workflow in WorkflowFramework().workflows:
            if workflow.name != flaw.osim_workflow:
                for state in workflow.states:
                    if state.name != flaw.osim_state:
                        new_stored_workflow = workflow.name
                        new_stored_state = state.name
                        flaw.classification = {
                            "workflow": new_stored_workflow,
                            "state": new_stored_state,
                        }

        # stored classification has changed
        assert flaw.osim_workflow == new_stored_workflow
        assert flaw.osim_workflow == flaw.classification["workflow"]
        assert flaw.osim_state == new_stored_state
        assert flaw.osim_state == flaw.classification["state"]
        # computed classification has not changed
        new_computed_workflow = flaw.classify()["workflow"]
        new_computed_state = flaw.classify()["state"]
        assert old_computed_workflow == new_computed_workflow
        assert old_computed_state == new_computed_state
        assert flaw.osim_workflow != new_computed_workflow
        assert flaw.osim_state != new_computed_state

    def test_adjust(self):
        """test flaw classification adjustion after metadata change"""
        workflow_framework = WorkflowFramework()
        random_states, _ = StateFactory().generate(count=1)
        random_states[0].requirements = []  # default state

        # initialize default workflow first so there is
        # always some workflow to classify the flaw in
        workflow = Workflow(
            {
                "name": "default workflow",
                "description": "random description",
                "priority": 0,
                "conditions": [],
                "states": [],  # this is not valid but OK for this test
            }
        )
        workflow.states = random_states
        workflow_framework.register_workflow(workflow)

        # major incident workflow
        workflow = Workflow(
            {
                "name": "major incident workflow",
                "description": "random description",
                "priority": 1,  # is more prior than default one
                "conditions": [
                    "major_incident"
                ],  # major incident flaws are classified here
                "states": [],  # this is not valid but OK for this test
            }
        )
        workflow.states = random_states
        workflow_framework.register_workflow(workflow)

        flaw = FlawFactory.build(is_major_incident=True)
        flaw.save(raise_validation_error=False)

        AffectFactory(flaw=flaw)
        FlawMetaFactory(
            flaw=flaw,
            type=FlawMeta.FlawMetaType.REQUIRES_SUMMARY,
            meta_attr={"status": "-"},
        )

        assert flaw.classification == {
            "workflow": "major incident workflow",
            "state": "DRAFT",
        }

        flaw.is_major_incident = False
        flaw.adjust_classification()
        assert flaw.classification == {
            "workflow": "default workflow",
            "state": "DRAFT",
        }

        # also test that adjust operation is idempotent
        flaw.adjust_classification()
        assert flaw.classification == {
            "workflow": "default workflow",
            "state": "DRAFT",
        }

    def test_adjust_no_change(self):
        """test that adjusting classification has no effect without flaw modification"""
        flaw = FlawFactory()  # random flaw
        classification = flaw.classification
        flaw.adjust_classification()
        assert classification == flaw.classification

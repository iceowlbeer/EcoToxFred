from __future__ import annotations

import os
import re
from typing import List, Iterable, Type
from langchain_core.prompts import PromptTemplate

import yaml
from pydantic import BaseModel
from sqlalchemy.util import classproperty

current_file_path = os.path.abspath(__file__)
current_directory = os.path.dirname(current_file_path)
prompts_directory = os.path.join(current_directory, 'prompts')

graph_metadata_file = os.path.join(prompts_directory, "graph_schema_metadata.yml")


class ToolDescriptions:
    _yaml_content = None

    @classmethod
    def get(cls, model_class: str, field_name: str) -> str:
        if cls._yaml_content is None:
            with open(os.path.join(prompts_directory, "tool_descriptions.yml")) as file:
                cls._yaml_content = yaml.safe_load(file)
        return cls._yaml_content[model_class][field_name]


class DefaultDict(dict):
    """Helper class to allow default values for a dictionary

    This is necessary to replace only some placeholders in an f-string.
    """

    def __missing__(self, key):
        return f"{{{key}}}"


class Prompt:
    """
    A Prompt is created from one specific YAML file that must have the following structure:

    parameters:
      - schema
      - examples
      - question
    prompt: |+
      Write your prompt here using newlines and the parameters like {schema} as you like.
    """

    def __init__(self, prompt_file: str):
        with open(prompt_file) as f:
            self.data = yaml.safe_load(f)
        self.prompt = self.data['prompt']
        if "parameters" in self.data.keys() and self.data['parameters'] is not None:
            self.parameters = set(self.data['parameters'])
        else:
            self.parameters = set()
        self.prompt_name = os.path.splitext(os.path.basename(prompt_file))[0]
        if not re.match(r"[a-z_]+", self.prompt_name):
            raise ValueError("File name of the prompt file must only contain letters and underscores.")

    def append(self, other: Prompt):
        if self is other:
            raise MemoryError("Cannot append the same Prompt to itself!")
        self.prompt += "\n" + other.prompt
        self.parameters = self.parameters.union(other.parameters)

    def inject_examples(self, examples: CypherExampleCollection):
        assert len(examples.examples) > 0
        placeholder_name = examples.get_placeholder_name()
        assert placeholder_name in self.parameters
        self.partial_apply({placeholder_name: examples.format_examples_as_markdown()})

    def has_parameter(self, parameter: str) -> bool:
        return parameter in self.parameters

    def has_parameters(self, parameters: Iterable) -> bool:
        return set(parameters).issubset(self.parameters)

    def partial_apply_prompt(self, prompt: Prompt):
        self.partial_apply({prompt.prompt_name: prompt.prompt})
        self.parameters = self.parameters.union(prompt.parameters)

    def partial_apply(self, parameters: dict):
        params_key_set = set(parameters.keys())
        assert params_key_set.issubset(set(self.parameters))
        self.prompt = self.prompt.format_map(DefaultDict(parameters))
        self.parameters = set(self.parameters) - params_key_set

    def get_prompt_template(self) -> PromptTemplate:
        return PromptTemplate(input_variable=list(self.parameters), template=self.prompt)


# noinspection PyMethodParameters
class Prompts:
    """
    Helper class to get easy access to all prompts.

    If you add another prompt YAML file, please add the appropriate classproperty here as well.
    Also, if we create partial prompts that we need to build up by merging them,
    this would be the right place for it.
    """

    _cached_prompts = {}

    @classproperty
    def agent(cls) -> Prompt:
        """
        Provides the prompt for the agent that orchestrates all tools and delivers the final answers.
        """
        if "agent" not in cls._cached_prompts.keys():
            basic_intro = Prompt(os.path.join(prompts_directory, "agent_prompt.yml"))
            cls._cached_prompts["agent"] = basic_intro
        return cls._cached_prompts["agent"]

    @classproperty
    def cypher_search(cls) -> Prompt:
        """
        Provides the prompt used for general graph database queries.
        This is used with a Cypher QA chain, and the agent relies on it when it wants to provide a text answer.
        """
        if "cypher_search" not in cls._cached_prompts.keys():
            # create plotmap specific prompt with injected few-shot examples
            csearch_prompt = Prompt(os.path.join(prompts_directory, "cyphersearch_prompt.yml"))
            csearch_prompt.inject_examples(CypherExampleCollections.general_cypher_queries)
            # create general cypher prompt with included schema metadata
            prompt_cypher_search = Prompt(os.path.join(prompts_directory, "cypher_prompt.yml"))
            prompt_cypher_search.partial_apply({"meta": get_graph_meta_data()})
            # combine general cypher prompt with cypher search prompt
            prompt_cypher_search.append(csearch_prompt)
            cls._cached_prompts["cypher_search"] = prompt_cypher_search
        return cls._cached_prompts["cypher_search"]

    @classproperty
    def geographic_map(cls) -> Prompt:
        """
        Provides the prompt used for graph database queries that access data for plotting on a map.
        The agent relies on it when it wants to provide an image of a map with annotated points.
        """
        if "geographic_map" not in cls._cached_prompts.keys():
            # create plotmap specific prompt with injected few-shot examples
            map_prompt = Prompt(os.path.join(prompts_directory, "geographicmap_prompt.yml"))
            map_prompt.inject_examples(CypherExampleCollections.map_cypher_queries)
            # create general cypher prompt with included schema metadata
            prompt_geographic_map = Prompt(os.path.join(prompts_directory, "cypher_prompt.yml"))
            prompt_geographic_map.partial_apply({"meta": get_graph_meta_data()})
            # combine general cypher prompt with plotmap prompt
            prompt_geographic_map.append(map_prompt)
            cls._cached_prompts["geographic_map"] = prompt_geographic_map
        return cls._cached_prompts["geographic_map"]

    @classproperty
    def scientific_plot(cls) -> Prompt:
        """
        Provides the prompt used for graph database queries that access data for plotting a two-dimensional scatter
        plot. The agent relies on it when it wants to provide an image of scientific two-dimensional plot with time
        or site names on the x-axis and any kind of numeric values on the y-axis. Numeric values can be mean or
        median concentrations, toxic units or summarized toxic units ([sum,ratio,max]TU), or driver importance values.
        """
        if "scientific_plot" not in cls._cached_prompts.keys():
            # create sciplot specific prompt with injected few-shot examples
            plot_prompt = Prompt(os.path.join(prompts_directory, "scientificplot_prompt.yml"))
            plot_prompt.inject_examples(CypherExampleCollections.plot_cypher_queries)
            # create general cypher prompt with included schema metadata, again???
            prompt_scientific_plot = Prompt(os.path.join(prompts_directory, "cypher_prompt.yml"))
            prompt_scientific_plot.partial_apply({"meta": get_graph_meta_data()})
            # combine general cypher prompt with plotmap prompt
            prompt_scientific_plot.append(plot_prompt)
            cls._cached_prompts["scientific_plot"] = prompt_scientific_plot
        return cls._cached_prompts["scientific_plot"]


class CypherExampleCollection:
    """
    CypherExampleCollection class for processing and organizing Cypher query examples from a specified file.

    It holds a number of example Cypher queries together with their corresponding descriptions.
    It can format these examples as a block of Markdown code to inject them into a prompt.
    """

    def __init__(self, example_file: str):
        """
        Reads a Cypher example file.

        :param example_file: Path to the example file.
            The file name must only contain letters and underscores.
        """
        self.examples: List[dict] = []
        self.read_cypher_file(example_file)
        self.example_name = os.path.splitext(os.path.basename(example_file))[0]
        if not re.match(r"[a-z_]+", self.example_name):
            raise ValueError("File name of the example file must only contain letters and underscores.")

    def get_queries(self) -> List[str]:
        """Returns the list of Cypher queries for this collection."""
        return [e["cypher"] for e in self.examples]

    def get_placeholder_name(self):
        """
        Returns the name of the file where the Cypher examples were read from.

        We assume that the f-string placeholder used in the prompt file has the same name.
        """
        return self.example_name

    def format_examples_as_markdown(self) -> str:
        result_lines = []
        for i in range(len(self.examples)):
            result_lines.append(f"{i}. {self.examples[i]['information']}")
            result_lines.append("```cypher")
            result_lines.append(self.examples[i]['cypher'])
            # if i < len(self.examples) - 1: # todo: @PS why did you do this? resulted in the omission of backticks for the last example
            result_lines.append("```\n")
        return "\n".join(result_lines)

    def read_cypher_file(self, file_path):
        """
        Opens and processes an example file.
        """
        with open(file_path) as file:
            content = file.read()

        # Split sections by one or more blank lines
        sections = re.split(r'\n\s*\n', content.strip())

        for section in sections:
            lines = section.strip().split('\n')
            information = []
            cypher = []

            # Separate comments from Cypher queries
            for line in lines:
                if line.startswith('//'):
                    information.append(line[2:].strip())
                else:
                    cypher.append(line.strip())

            # Join comment lines and query lines respectively
            info_str = '\n'.join(information)
            cypher_str = '\n'.join(cypher)

            self.examples.append({"information": info_str, "cypher": cypher_str})


class CypherExampleCollections:
    """
    Provides access to all Cypher example collections.
    """

    @classproperty
    def general_cypher_queries(self) -> CypherExampleCollection:
        """
        Provides a collection of Cypher examples for the general case typically used to access a limited number of
        results that can be presented in text form.
        """
        return CypherExampleCollection(os.path.join(prompts_directory, "cyphersearch_examples.cypher"))

    @classproperty
    def map_cypher_queries(self) -> CypherExampleCollection:
        """
        Provides a collection of Cypher examples for drawing points on a map.
        This can give in a large number of results.
        """
        return CypherExampleCollection(os.path.join(prompts_directory, "geographicmap_examples.cypher"))

    @classproperty
    def plot_cypher_queries(self) -> CypherExampleCollection:
        """
        Provides a collection of Cypher examples used for drawing charts.
        This can give in a large number of results.
        """
        return CypherExampleCollection(os.path.join(prompts_directory, "scientificplot_examples.cypher"))


def get_graph_meta_data() -> str:
    """
    Reads the graph metadata from a specified file.

    :return: Graph metadata as a string.
    """
    with open(graph_metadata_file) as f:
        meta = f.read()
    return meta

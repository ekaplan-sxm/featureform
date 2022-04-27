# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

from typing import List, Tuple, Union
from typeguard import typechecked
from dataclasses import dataclass
import metadata_pb2 as pb
import grpc
import json

NameVariant = Tuple[str, str]


@typechecked
def valid_name_variant(nvar: NameVariant) -> bool:
    return nvar[0] != "" and nvar[1] != ""


@typechecked
@dataclass
class RedisConfig:
    host: str
    port: int
    password: str
    db: int

    def software(self) -> str:
        return "redis"


@typechecked
@dataclass
class SnowflakeConfig:
    account: str
    database: str
    organization: str
    username: str
    password: str
    schema: str

    def software(self) -> str:
        return "Snowflake"

    def type(self) -> str:
        return "SNOWFLAKE_OFFLINE"

    def serialize(self) -> bytes:
        config = {
            "Username": self.username,
            "Password": self.password,
            "Organization": self.organization,
            "Account": self.account,
            "Database": self.database,
        }
        return bytes(json.dumps(config), "utf-8")


@typechecked
@dataclass
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str

    def software(self) -> str:
        return "postgres"


Config = Union[RedisConfig, SnowflakeConfig, PostgresConfig]


@typechecked
@dataclass
class Provider:
    name: str
    function: str
    config: Config
    description: str
    team: str

    def __post_init__(self):
        self.software = self.config.software()

    @staticmethod
    def type() -> str:
        return "provider"

    def _create(self, stub) -> None:
        serialized = pb.Provider(
            name=self.name,
            description=self.description,
            type=self.config.type(),
            software=self.config.software(),
            team=self.team,
            serialized_config=self.config.serialize(),
        )
        stub.CreateProvider(serialized)


@typechecked
@dataclass
class User:
    name: str

    def type(self) -> str:
        return "user"

    def _create(self, stub) -> None:
        serialized = pb.User(name=self.name)
        stub.CreateUser(serialized)


@typechecked
@dataclass
class SQLTable:
    name: str


Location = SQLTable


@typechecked
@dataclass
class PrimaryData:
    location: Location

    def kwargs(self):
        return {
            "primaryData":
                pb.PrimaryData(table=pb.PrimarySQLTable(
                    name=self.location.name,),),
        }


class Transformation:
    pass


@typechecked
@dataclass
class SQLTransformation(Transformation):
    query: str

    def type():
        "SQL"

    def kwargs(self):
        return {
            "transformation":
                pb.Transformation(SQLTransformation=pb.SQLTransformation(
                    query=self.query,),),
        }


SourceDefinition = Union[PrimaryData, Transformation]


@typechecked
@dataclass
class Source:
    name: str
    variant: str
    definition: SourceDefinition
    owner: str
    provider: str
    description: str

    @staticmethod
    def type() -> str:
        return "source"

    def _create(self, stub) -> None:
        defArgs = self.definition.kwargs()
        serialized = pb.SourceVariant(
            name=self.name,
            variant=self.variant,
            owner=self.owner,
            description=self.description,
            provider=self.provider,
            **defArgs,
        )
        stub.CreateSourceVariant(serialized)


@typechecked
@dataclass
class Entity:
    name: str
    description: str

    @staticmethod
    def type() -> str:
        return "entity"


@typechecked
@dataclass
class ResourceColumnMapping:
    entity: str
    value: str
    timestamp: str


ResourceLocation = ResourceColumnMapping


@typechecked
@dataclass
class Feature:
    name: str
    variant: str
    value_type: str
    entity: str
    owner: str
    provider: str
    description: str
    location: ResourceLocation

    @staticmethod
    def type() -> str:
        return "feature"


@typechecked
@dataclass
class Label:
    name: str
    variant: str
    value_type: str
    entity: str
    owner: str
    description: str
    location: ResourceLocation

    @staticmethod
    def type() -> str:
        return "label"


@typechecked
@dataclass
class TrainingSet:
    name: str
    variant: str
    owner: str
    label: NameVariant
    features: List[NameVariant]
    description: str

    def __post_init__(self):
        if not valid_name_variant(self.label):
            raise ValueError("Label must be set")
        if len(self.features) == 0:
            raise ValueError("A training-set must have atleast one feature")
        for feature in self.features:
            if not valid_name_variant(feature):
                raise ValueError("Invalid Feature")

    @staticmethod
    def type() -> str:
        return "training-set"


Resource = Union[PrimaryData, Provider, Entity, User, Feature, Label,
                 TrainingSet, Source]


class ResourceRedefinedError(Exception):

    @typechecked
    def __init__(self, resource: Resource):
        variantStr = f" variant {resource.variant}" if hasattr(
            resource, 'variant') else ""
        resourceId = f"{resource.name}{variantStr}"
        super().__init__(
            f"{resource.type()} resource {resourceId} defined in multiple places"
        )


class ResourceState:

    def __init__(self):
        self.__state = {}
        self.__create_list = []

    @typechecked
    def add(self, resource: Resource) -> None:
        key = (resource.type(), resource.name)
        if key in self.__state:
            raise ResourceRedefinedError(resource)
        self.__state[key] = resource
        self.__create_list.append(resource)

    def sorted_list(self) -> List[Resource]:
        resource_order = {
            "user": 0,
            "provider": 1,
            "source": 2,
            "entity": 3,
            "feature": 4,
            "label": 5,
            "training-set": 6,
        }

        def to_sort_key(res):
            resource_num = resource_order[res.type()]
            variant = res.variant if hasattr(res, "variant") else ""
            return (resource_num, res.name, variant)

        return sorted(self.__state.values(), key=to_sort_key)

    def create_all(self, stub) -> None:
        for resource in self.__create_list:
            try:
                print("Creating ", resource.name)
                resource._create(stub)
            except grpc._channel._InactiveRpcError as e:
                print(resource.name, " already exists.")

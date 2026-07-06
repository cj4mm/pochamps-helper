from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RateEntry(BaseModel):
    name: str
    rate: Optional[float] = None
    description: Optional[str] = None


class StatAllocation(BaseModel):
    rate: Optional[float] = None
    hp: Optional[int] = None
    atk: Optional[int] = None
    defense: Optional[int] = None
    spa: Optional[int] = None
    spd: Optional[int] = None
    spe: Optional[int] = None
    label: Optional[str] = None
    raw: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class PokemonSummary(BaseModel):
    role: Optional[str] = None
    common_moves: List[RateEntry] = Field(default_factory=list)
    common_items: List[RateEntry] = Field(default_factory=list)
    common_abilities: List[RateEntry] = Field(default_factory=list)
    common_natures: List[RateEntry] = Field(default_factory=list)
    common_evs: List[str] = Field(default_factory=list)
    common_stat_allocations: List[StatAllocation] = Field(default_factory=list)
    stat_allocation_notes: List[str] = Field(default_factory=list)
    partners: List[RateEntry] = Field(default_factory=list)
    winning_matchups: List[RateEntry] = Field(default_factory=list)
    losing_matchups: List[RateEntry] = Field(default_factory=list)
    raw: Dict[str, Any] = Field(default_factory=dict)


class PokemonMeta(BaseModel):
    pokemon: str
    ko_name: Optional[str] = None
    slug: str
    source: str
    updated_at: Optional[str] = None
    battle_format: str = "single"
    data_quality: str = "cache"
    summary: PokemonSummary
    notes: Optional[str] = None

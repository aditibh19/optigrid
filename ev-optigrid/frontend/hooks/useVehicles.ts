"use client";
import { useCallback, useEffect, useState } from "react";
import { createVehicle, listVehicles, type Vehicle, type VehicleInput } from "@/services/api";

const KEY = "evoptigrid.selected-vehicle";

export const DEFAULT_VEHICLE: VehicleInput = {
  make: "Tata", model: "Nexon EV", battery_capacity_kwh: 40.5,
  efficiency_kwh_per_km: 0.16, max_charge_rate_kw: 50, current_soc: 32,
};

/** The signed-in user's vehicles, plus which one is selected (remembered across pages). */
export function useVehicles() {
  const [vehicles, setVehicles] = useState<Vehicle[] | null>(null);   // null = still loading
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async (preferId?: string) => {
    try {
      const list = await listVehicles();
      let remembered: string | null = null;
      try { remembered = window.localStorage.getItem(KEY); } catch { /* storage blocked */ }
      const wanted = preferId ?? remembered;
      setVehicles(list);
      setSelectedId(list.find((v) => v.id === wanted)?.id ?? list[0]?.id ?? null);
      setError(null);
    } catch (e) {
      setVehicles([]);
      setError(e instanceof Error ? e.message : "Couldn't load vehicles.");
    }
  }, []);

  useEffect(() => { void reload(); }, [reload]);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    try { window.localStorage.setItem(KEY, id); } catch { /* storage blocked */ }
  }, []);

  const add = useCallback(async (input: VehicleInput) => {
    const created = await createVehicle(input);
    try { window.localStorage.setItem(KEY, created.id); } catch { /* storage blocked */ }
    await reload(created.id);
    return created;
  }, [reload]);

  const selected = vehicles?.find((v) => v.id === selectedId) ?? null;
  return { vehicles, selected, selectedId, select, add, reload, error };
}

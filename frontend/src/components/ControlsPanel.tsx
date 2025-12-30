import React from "react";

export type ViewMode = "bus" | "substation" | "station_detail";

export type ControlsPanelProps = {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  centerBus: number | null;
  onCenterBusChange: (bus: number | null) => void;
  degrees: number;
  onDegreesChange: (degrees: number) => void;
  showEquipment: boolean;
  onShowEquipmentChange: (show: boolean) => void;
  showSubstationGroups: boolean;
  onShowSubstationGroupsChange: (show: boolean) => void;
  optimizeLayout: boolean;
  onOptimizeLayoutChange: (optimize: boolean) => void;
  onReset: () => void;
  onReLayout: () => void;
};

const ControlsPanel: React.FC<ControlsPanelProps> = ({
  viewMode,
  onViewModeChange,
  centerBus,
  onCenterBusChange,
  degrees,
  onDegreesChange,
  showEquipment,
  onShowEquipmentChange,
  showSubstationGroups,
  onShowSubstationGroupsChange,
  optimizeLayout,
  onOptimizeLayoutChange,
  onReset,
  onReLayout,
}) => {
  return (
    <div
      style={{
        position: "absolute",
        top: "10px",
        right: "10px",
        background: "rgba(255, 255, 255, 0.95)",
        padding: "10px 14px",
        borderRadius: "6px",
        fontSize: "12px",
        zIndex: 1000,
        boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
        display: "flex",
        gap: "12px",
        alignItems: "center",
        flexWrap: "wrap",
        maxWidth: "calc(100% - 40px)",
      }}
    >
      <div>
        <label>Mode: </label>
        <select
          value={viewMode}
          onChange={(e) => onViewModeChange(e.target.value as ViewMode)}
          style={{ padding: "4px" }}
        >
          <option value="bus">Bus</option>
          <option value="substation">Substation</option>
          <option value="station_detail">Station Detail</option>
        </select>
      </div>
      <div>
        <label>Center: </label>
        <input
          type="number"
          value={centerBus ?? ""}
          placeholder="(auto)"
          onChange={(e) => {
            const v = e.target.value;
            onCenterBusChange(v === "" ? null : Number(v));
          }}
          style={{ width: "90px", padding: "4px" }}
          disabled={viewMode === "substation"}
          title={viewMode === "substation" ? "Center bus not used in substation mode" : ""}
        />
      </div>
      <div>
        <label>Degrees: </label>
        <input
          type="number"
          min={0}
          max={10}
          value={degrees}
          onChange={(e) => onDegreesChange(Number(e.target.value))}
          style={{ width: "50px", padding: "4px" }}
        />
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
        <input
          type="checkbox"
          checked={showEquipment}
          onChange={(e) => onShowEquipmentChange(e.target.checked)}
        />
        Equipment
      </label>
      <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
        <input
          type="checkbox"
          checked={showSubstationGroups}
          onChange={(e) => onShowSubstationGroupsChange(e.target.checked)}
        />
        Substations
      </label>
      <label style={{ display: "flex", alignItems: "center", gap: "4px" }}>
        <input
          type="checkbox"
          checked={optimizeLayout}
          onChange={(e) => onOptimizeLayoutChange(e.target.checked)}
        />
        Optimize
      </label>
      <button
        onClick={onReset}
        style={{
          padding: "4px 10px",
          fontSize: "12px",
          cursor: "pointer",
          background: "#3498db",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
        }}
      >
        Reset
      </button>
      <button
        onClick={onReLayout}
        style={{
          padding: "4px 10px",
          fontSize: "12px",
          cursor: "pointer",
          background: "#e74c3c",
          color: "#fff",
          border: "none",
          borderRadius: "4px",
        }}
        title="Force layout recalculation"
      >
        Re-layout
      </button>
    </div>
  );
};

export default ControlsPanel;

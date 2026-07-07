const { useState, useEffect, useRef } = React;

// Helper: Indian style number formatting
function formatIndian(n, dec = 0) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    const neg = n < 0;
    n = Math.abs(parseFloat(n));
    const whole = Math.floor(n);
    const frac = n - whole;
    let s = whole.toString();
    if (s.length > 3) {
        let head = s.slice(0, -3);
        const tail = s.slice(-3);
        const parts = [];
        while (head.length > 2) {
            parts.unshift(head.slice(-2));
            head = head.slice(0, -2);
        }
        if (head) parts.unshift(head);
        s = parts.join(",") + "," + tail;
    }
    if (dec > 0) {
        s += "." + Math.round(frac * Math.pow(10, dec)).toString().padEnd(dec, "0");
    }
    return (neg ? "-" : "") + s;
}

function formatPct(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return parseFloat(n).toFixed(2) + "%";
}

function formatPp(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    const sign = n >= 0 ? "+" : "";
    return sign + parseFloat(n).toFixed(2);
}

function formatGrowth(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    const arrow = n > 0 ? "↑ " : (n < 0 ? "↓ " : "");
    return arrow + Math.abs(parseFloat(n)).toFixed(2) + "%";
}

function getGrowthColor(n) {
    if (n === null || n === undefined || isNaN(n) || n === 0) return "";
    return n > 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold";
}

function App() {
    const [activeTab, setActiveTab] = useState("overview");
    const [filterOptions, setFilterOptions] = useState({
        districts: [],
        rsas: [],
        coms: [],
        hwy_types: [],
        hwy_nos: [],
        tas: [],
        fys: []
    });

    // Filters state
    const [product, setProduct] = useState("MS");
    const [cy, setCy] = useState("2025-26");
    const [ly, setLy] = useState("2024-25");
    const [months, setMonths] = useState([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]);
    const [selDistricts, setSelDistricts] = useState([]);
    const [selRsas, setSelRsas] = useState([]);
    const [selComs, setSelComs] = useState([]);
    const [selHwyNos, setSelHwyNos] = useState([]);
    const [universe, setUniverse] = useState("Industry");

    // TA Profile specific state
    const [selectedTa, setSelectedTa] = useState("T02-005"); // Default TA
    const [taData, setTaData] = useState(null);

    // Data states
    const [overviewData, setOverviewData] = useState(null);
    const [performanceData, setPerformanceData] = useState(null);
    const [loading, setLoading] = useState(false);

    // Chart ref
    const chartRef = useRef(null);
    const chartInstance = useRef(null);

    // Fetch filters on load
    useEffect(() => {
        fetch("/api/filters")
            .then(res => res.json())
            .then(data => {
                setFilterOptions(data);
                if (data.fys && data.fys.length >= 2) {
                    setCy(data.fys[data.fys.length - 1]);
                    setLy(data.fys[data.fys.length - 2]);
                }
            });
    }, []);

    // Helper to serialize filters for API request
    const getQueryString = () => {
        const params = new URLSearchParams({
            product,
            cy,
            ly,
            months: months.join(","),
            districts: selDistricts.join(","),
            rsas: selRsas.join(","),
            coms: selComs.join(","),
            hwy_nos: selHwyNos.join(","),
            universe
        });
        return params.toString();
    };

    // Load active tab data
    useEffect(() => {
        if (!cy) return;
        setLoading(true);
        const query = getQueryString();

        if (activeTab === "overview") {
            fetch(`/api/overview?${query}`)
                .then(res => res.json())
                .then(data => {
                    setOverviewData(data);
                    setLoading(false);
                });
        } else if (activeTab === "performance") {
            fetch(`/api/performance?${query}`)
                .then(res => res.json())
                .then(data => {
                    setPerformanceData(data);
                    setLoading(false);
                });
        } else if (activeTab === "ta_profile") {
            fetch(`/api/ta_profile?ta_code=${selectedTa}&product=${product}&cy=${cy}&ly=${ly}&months=${months.join(",")}`)
                .then(res => res.json())
                .then(data => {
                    setTaData(data);
                    setLoading(false);
                });
        }
    }, [activeTab, product, cy, ly, months, selDistricts, selRsas, selComs, selHwyNos, universe, selectedTa]);

    // Render Overview Chart
    useEffect(() => {
        if (activeTab === "overview" && overviewData && chartRef.current) {
            const ctx = chartRef.current.getContext("2d");
            if (chartInstance.current) {
                chartInstance.current.destroy();
            }

            const labels = overviewData.table.map(r => r.omc);
            const shares = overviewData.table.map(r => r.share || 0);
            const colors = overviewData.table.map(r => overviewData.omc_colors[r.omc] || "#888");

            chartInstance.current = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Market Share %',
                        data: shares,
                        backgroundColor: colors,
                        borderWidth: 0,
                        borderRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            grid: { color: 'rgba(255, 255, 255, 0.1)' },
                            ticks: { color: '#94a3b8' }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#94a3b8' }
                        }
                    }
                }
            });
        }
    }, [activeTab, overviewData]);

    return (
        <div className="flex min-h-screen bg-slate-950 text-slate-100">
            {/* Sidebar */}
            <div className="w-80 bg-slate-900 border-r border-slate-800 p-6 flex flex-col gap-6 shrink-0">
                <div className="flex items-center gap-3">
                    <span className="text-2xl">⛽</span>
                    <div>
                        <h1 className="font-bold text-lg text-slate-50">Pune DO</h1>
                        <p className="text-xs text-slate-400">Option A Trial (React SPA)</p>
                    </div>
                </div>

                <div className="flex flex-col gap-1">
                    <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Navigation</label>
                    <button 
                        onClick={() => setActiveTab("overview")}
                        className={`text-left px-3 py-2 rounded-lg text-sm transition ${activeTab === 'overview' ? 'bg-orange-500 font-semibold text-white' : 'text-slate-300 hover:bg-slate-800'}`}
                    >
                        📊 Overview
                    </button>
                    <button 
                        onClick={() => setActiveTab("performance")}
                        className={`text-left px-3 py-2 rounded-lg text-sm transition ${activeTab === 'performance' ? 'bg-orange-500 font-semibold text-white' : 'text-slate-300 hover:bg-slate-800'}`}
                    >
                        📈 Performance (CY vs LY)
                    </button>
                    <button 
                        onClick={() => setActiveTab("ta_profile")}
                        className={`text-left px-3 py-2 rounded-lg text-sm transition ${activeTab === 'ta_profile' ? 'bg-orange-500 font-semibold text-white' : 'text-slate-300 hover:bg-slate-800'}`}
                    >
                        🗺️ TA Profile (PPT Grid)
                    </button>
                </div>

                {/* Sidebar Filters */}
                <div className="flex flex-col gap-4 border-t border-slate-800 pt-4 overflow-y-auto max-h-[60vh]">
                    <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Filters</h2>

                    <div>
                        <label className="block text-xs text-slate-400 mb-1">Product</label>
                        <select 
                            value={product} 
                            onChange={(e) => setProduct(e.target.value)}
                            className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-sm text-slate-100"
                        >
                            <option value="MS">MS (Petrol)</option>
                            <option value="HSD">HSD (Diesel)</option>
                        </select>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <label className="block text-xs text-slate-400 mb-1">CY</label>
                            <select 
                                value={cy} 
                                onChange={(e) => setCy(e.target.value)}
                                className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-sm text-slate-100"
                            >
                                {filterOptions.fys.map(fy => (
                                    <option key={fy} value={fy}>{fy}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs text-slate-400 mb-1">LY</label>
                            <select 
                                value={ly} 
                                onChange={(e) => setLy(e.target.value)}
                                className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-sm text-slate-100"
                            >
                                <option value="">None</option>
                                {filterOptions.fys.map(fy => (
                                    <option key={fy} value={fy}>{fy}</option>
                                ))}
                            </select>
                        </div>
                    </div>

                    <div>
                        <label className="block text-xs text-slate-400 mb-1">Period type</label>
                        <select 
                            onChange={(e) => {
                                const val = e.target.value;
                                if (val === "full") setMonths([1,2,3,4,5,6,7,8,9,10,11,12]);
                                else if (val === "q1") setMonths([1,2,3]);
                                else if (val === "q2") setMonths([4,5,6]);
                                else if (val === "q3") setMonths([7,8,9]);
                                else if (val === "q4") setMonths([10,11,12]);
                            }}
                            className="w-full bg-slate-800 border border-slate-700 rounded p-2 text-sm text-slate-100"
                        >
                            <option value="full">Full Year (Apr - Mar)</option>
                            <option value="q1">Q1 (Apr - Jun)</option>
                            <option value="q2">Q2 (Jul - Sep)</option>
                            <option value="q3">Q3 (Oct - Dec)</option>
                            <option value="q4">Q4 (Jan - Mar)</option>
                        </select>
                    </div>

                    {/* Multi-select inputs (standard select multiple) */}
                    <div>
                        <label className="block text-xs text-slate-400 mb-1">Districts</label>
                        <select 
                            multiple
                            value={selDistricts}
                            onChange={(e) => {
                                const options = [...e.target.selectedOptions].map(o => o.value);
                                setSelDistricts(options);
                            }}
                            className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-xs text-slate-100 h-20"
                        >
                            {filterOptions.districts.map(d => (
                                <option key={d} value={d}>{d}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-xs text-slate-400 mb-1">Sales Area (RSA)</label>
                        <select 
                            multiple
                            value={selRsas}
                            onChange={(e) => {
                                const options = [...e.target.selectedOptions].map(o => o.value);
                                setSelRsas(options);
                            }}
                            className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-xs text-slate-100 h-20"
                        >
                            {filterOptions.rsas.map(r => (
                                <option key={r.code} value={r.code}>{r.name}</option>
                            ))}
                        </select>
                    </div>

                    <div>
                        <label className="block text-xs text-slate-400 mb-1">COM</label>
                        <select 
                            multiple
                            value={selComs}
                            onChange={(e) => {
                                const options = [...e.target.selectedOptions].map(o => o.value);
                                setSelComs(options);
                            }}
                            className="w-full bg-slate-800 border border-slate-700 rounded p-1 text-xs text-slate-100 h-20"
                        >
                            {filterOptions.coms.map(c => (
                                <option key={c} value={c}>{c}</option>
                            ))}
                        </select>
                    </div>
                </div>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 p-8 flex flex-col gap-6 overflow-y-auto max-h-screen">
                <div className="flex justify-between items-center border-b border-slate-800 pb-4">
                    <div>
                        <h2 className="text-xl font-bold text-slate-100 uppercase">
                            {activeTab.replace("_", " ")}
                        </h2>
                        <p className="text-xs text-slate-400 mt-1">
                            {product} · CY: {cy} {ly ? `vs LY: ${ly}` : ''}
                        </p>
                    </div>
                    {loading && (
                        <div className="text-sm text-orange-400 font-semibold animate-pulse">
                            ⚡ Querying DB...
                        </div>
                    )}
                </div>

                {/* Tab content renders */}
                {activeTab === "overview" && overviewData && (
                    <div className="flex flex-col gap-6">
                        {/* KPI Cards */}
                        <div className="grid grid-cols-5 gap-4">
                            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                                <h3 className="text-xs text-slate-400 uppercase tracking-wide">IOCL Vol (KL)</h3>
                                <p className="text-2xl font-bold mt-2">{formatIndian(overviewData.kpis.iocl_vol_cy, 0)}</p>
                                <p className={`text-xs mt-1 ${getGrowthColor(overviewData.kpis.iocl_gr)}`}>
                                    {formatGrowth(overviewData.kpis.iocl_gr)} vs LY
                                </p>
                            </div>
                            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                                <h3 className="text-xs text-slate-400 uppercase tracking-wide">IOCL Share %</h3>
                                <p className="text-2xl font-bold mt-2">{formatPct(overviewData.kpis.iocl_share_cy)}</p>
                                <p className={`text-xs mt-1 ${getGrowthColor(overviewData.kpis.iocl_share_ppt)}`}>
                                    {formatPp(overviewData.kpis.iocl_share_ppt)} pp
                                </p>
                            </div>
                            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                                <h3 className="text-xs text-slate-400 uppercase tracking-wide">Denominator Share %</h3>
                                <p className="text-2xl font-bold mt-2">{formatPct(overviewData.kpis.iocl_psu_share_cy)}</p>
                                <p className={`text-xs mt-1 ${getGrowthColor(overviewData.kpis.iocl_psu_share_ppt)}`}>
                                    {formatPp(overviewData.kpis.iocl_psu_share_ppt)} pp
                                </p>
                            </div>
                            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                                <h3 className="text-xs text-slate-400 uppercase tracking-wide">KLPM (KL/mo/RO)</h3>
                                <p className="text-2xl font-bold mt-2">{formatIndian(overviewData.kpis.iocl_klpm_cy, 2)}</p>
                                <p className={`text-xs mt-1 ${getGrowthColor(overviewData.kpis.iocl_klpm_diff)}`}>
                                    {formatPp(overviewData.kpis.iocl_klpm_diff)} vs LY
                                </p>
                            </div>
                            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-lg">
                                <h3 className="text-xs text-slate-400 uppercase tracking-wide">Outlets</h3>
                                <p className="text-2xl font-bold mt-2">{formatIndian(overviewData.kpis.iocl_outlets)}</p>
                            </div>
                        </div>

                        {/* Chart and Table */}
                        <div className="grid grid-cols-3 gap-6">
                            <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg">
                                <div className="flex justify-between items-center mb-4">
                                    <h3 className="font-semibold text-slate-100 uppercase">OMC Breakdown</h3>
                                    <div className="flex gap-2">
                                        <button 
                                            onClick={() => setUniverse("Industry")}
                                            className={`px-3 py-1 text-xs rounded border transition ${universe === 'Industry' ? 'bg-orange-500 border-orange-400 text-white' : 'border-slate-700 text-slate-400'}`}
                                        >
                                            Industry
                                        </button>
                                        <button 
                                            onClick={() => setUniverse("PSU")}
                                            className={`px-3 py-1 text-xs rounded border transition ${universe === 'PSU' ? 'bg-orange-500 border-orange-400 text-white' : 'border-slate-700 text-slate-400'}`}
                                        >
                                            PSU Only
                                        </button>
                                    </div>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-sm text-left border-collapse">
                                        <thead>
                                            <tr className="border-b border-slate-800 text-slate-400 font-medium">
                                                <th className="py-2 px-3">OMC</th>
                                                <th className="py-2 px-3 text-right">CY Vol (KL)</th>
                                                <th className="py-2 px-3 text-right">LY Vol (KL)</th>
                                                <th className="py-2 px-3 text-right">Growth %</th>
                                                <th className="py-2 px-3 text-right">Share %</th>
                                                <th className="py-2 px-3 text-right">+/- pp</th>
                                                <th className="py-2 px-3 text-right">PPT CY</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {overviewData.table.map(row => (
                                                <tr key={row.omc} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                                                    <td className="py-2 px-3 font-semibold text-slate-300">{row.omc}</td>
                                                    <td className="py-2 px-3 text-right">{formatIndian(row.cy_vol, 1)}</td>
                                                    <td className="py-2 px-3 text-right">{formatIndian(row.ly_vol, 1)}</td>
                                                    <td className={`py-2 px-3 text-right ${getGrowthColor(row.growth)}`}>
                                                        {formatGrowth(row.growth)}
                                                    </td>
                                                    <td className="py-2 px-3 text-right">{formatPct(row.share)}</td>
                                                    <td className={`py-2 px-3 text-right ${getGrowthColor(row.ppt)}`}>
                                                        {formatPp(row.ppt)}
                                                    </td>
                                                    <td className="py-2 px-3 text-right">{formatIndian(row.ppt_cy, 1)}</td>
                                                </tr>
                                            ))}
                                            <tr className="bg-slate-800/40 border-t-2 border-slate-700 font-bold">
                                                <td className="py-2 px-3 text-slate-100">Total</td>
                                                <td className="py-2 px-3 text-right">{formatIndian(overviewData.totals.cy_vol, 1)}</td>
                                                <td className="py-2 px-3 text-right">{formatIndian(overviewData.totals.ly_vol, 1)}</td>
                                                <td className={`py-2 px-3 text-right ${getGrowthColor(overviewData.totals.growth)}`}>
                                                    {formatGrowth(overviewData.totals.growth)}
                                                </td>
                                                <td className="py-2 px-3 text-right">—</td>
                                                <td className="py-2 px-3 text-right">—</td>
                                                <td className="py-2 px-3 text-right">{formatIndian(overviewData.totals.ppt_cy, 1)}</td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg flex flex-col">
                                <h3 className="font-semibold text-slate-100 uppercase mb-4">Market Share Chart</h3>
                                <div className="flex-1 relative h-64">
                                    <canvas ref={chartRef}></canvas>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === "performance" && performanceData && (
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="font-semibold text-slate-100 uppercase">Performance Summary Table</h3>
                            <div className="flex gap-2">
                                <button 
                                    onClick={() => setUniverse("Industry")}
                                    className={`px-3 py-1 text-xs rounded border transition ${universe === 'Industry' ? 'bg-orange-500 border-orange-400 text-white' : 'border-slate-700 text-slate-400'}`}
                                >
                                    Industry
                                </button>
                                <button 
                                    onClick={() => setUniverse("PSU")}
                                    className={`px-3 py-1 text-xs rounded border transition ${universe === 'PSU' ? 'bg-orange-500 border-orange-400 text-white' : 'border-slate-700 text-slate-400'}`}
                                >
                                    PSU Only
                                </button>
                            </div>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left border-collapse">
                                <thead>
                                    <tr className="border-b border-slate-800 text-slate-400 font-medium">
                                        <th className="py-3 px-3">OMC</th>
                                        <th className="py-3 px-3 text-right">Outlets</th>
                                        <th className="py-3 px-3 text-right">RO Part %</th>
                                        <th className="py-3 px-3 text-right">CY Vol (KL)</th>
                                        <th className="py-3 px-3 text-right">LY Vol (KL)</th>
                                        <th className="py-3 px-3 text-right">+/- (KL)</th>
                                        <th className="py-3 px-3 text-right">Growth %</th>
                                        <th className="py-3 px-3 text-right">KLPM CY</th>
                                        <th className="py-3 px-3 text-right">Share CY</th>
                                        <th className="py-3 px-3 text-right">Share LY</th>
                                        <th className="py-3 px-3 text-right">+/- pp</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {performanceData.table.map(row => (
                                        <tr key={row.omc} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                                            <td className="py-2.5 px-3 font-semibold text-slate-300">{row.omc}</td>
                                            <td className="py-2.5 px-3 text-right">{formatIndian(row.ros, 0)}</td>
                                            <td className="py-2.5 px-3 text-right">{formatPct(row.ro_part)}</td>
                                            <td className="py-2.5 px-3 text-right">{formatIndian(row.cy_vol, 1)}</td>
                                            <td className="py-2.5 px-3 text-right">{formatIndian(row.ly_vol, 1)}</td>
                                            <td className={`py-2.5 px-3 text-right ${getGrowthColor(row.diff_vol)}`}>
                                                {formatIndian(row.diff_vol, 1)}
                                            </td>
                                            <td className={`py-2.5 px-3 text-right ${getGrowthColor(row.gr)}`}>
                                                {formatGrowth(row.gr)}
                                            </td>
                                            <td className="py-2.5 px-3 text-right">{formatIndian(row.klpm_cy, 2)}</td>
                                            <td className="py-2.5 px-3 text-right">{formatPct(row.share_cy)}</td>
                                            <td className="py-2.5 px-3 text-right">{formatPct(row.share_ly)}</td>
                                            <td className={`py-2.5 px-3 text-right ${getGrowthColor(row.share_ppt)}`}>
                                                {formatPp(row.share_ppt)}
                                            </td>
                                        </tr>
                                    ))}
                                    {performanceData.subtotals.map(row => (
                                        <tr key={row.omc} className="bg-slate-800/40 border-t border-slate-700 font-bold">
                                            <td className="py-3 px-3 text-slate-100">{row.omc} Subtotal</td>
                                            <td className="py-3 px-3 text-right">{formatIndian(row.ros, 0)}</td>
                                            <td className="py-3 px-3 text-right">{formatPct(row.ro_part)}</td>
                                            <td className="py-3 px-3 text-right">{formatIndian(row.cy_vol, 1)}</td>
                                            <td className="py-3 px-3 text-right">{formatIndian(row.ly_vol, 1)}</td>
                                            <td className={`py-3 px-3 text-right ${getGrowthColor(row.diff_vol)}`}>
                                                {formatIndian(row.diff_vol, 1)}
                                            </td>
                                            <td className={`py-3 px-3 text-right ${getGrowthColor(row.gr)}`}>
                                                {formatGrowth(row.gr)}
                                            </td>
                                            <td className="py-3 px-3 text-right">{formatIndian(row.klpm_cy, 2)}</td>
                                            <td className="py-3 px-3 text-right">{formatPct(row.share_cy)}</td>
                                            <td className="py-3 px-3 text-right">{formatPct(row.share_ly)}</td>
                                            <td className={`py-3 px-3 text-right ${getGrowthColor(row.share_ppt)}`}>
                                                {formatPp(row.share_ppt)}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}

                {activeTab === "ta_profile" && (
                    <div className="flex flex-col gap-6">
                        {/* TA Select */}
                        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg">
                            <label className="block text-sm text-slate-400 mb-2 font-medium">Select Trading Area for Profile</label>
                            <select 
                                value={selectedTa} 
                                onChange={(e) => setSelectedTa(e.target.value)}
                                className="bg-slate-800 border border-slate-700 rounded p-2 text-sm text-slate-100 w-full max-w-md"
                            >
                                {filterOptions.tas.map(ta => (
                                    <option key={ta.code} value={ta.code}>{ta.code} — {ta.name}</option>
                                ))}
                            </select>
                        </div>

                        {taData && (
                            <div className="grid grid-cols-3 gap-6">
                                {/* Left Profile Card */}
                                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg flex flex-col gap-4">
                                    <h3 className="font-semibold text-slate-100 uppercase border-b border-slate-800 pb-2">Network Outlets</h3>
                                    <table className="w-full text-sm text-left border-collapse">
                                        <thead>
                                            <tr className="border-b border-slate-800 text-slate-400 font-medium">
                                                <th className="py-2">OMC</th>
                                                <th className="py-2 text-right">MS</th>
                                                <th className="py-2 text-right">HSD</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {taData.networks.map(row => (
                                                <tr key={row.omc} className={`border-b border-slate-800/30 ${row.omc === 'TOTAL' ? 'font-bold bg-slate-800/40' : ''}`}>
                                                    <td className="py-2 text-slate-300">{row.omc}</td>
                                                    <td className="py-2 text-right">{row.ms_outlets}</td>
                                                    <td className="py-2 text-right">{row.hsd_outlets}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>

                                    <h3 className="font-semibold text-slate-100 uppercase border-b border-slate-800 pb-2 mt-4">IOCL Share in TA</h3>
                                    <div className="grid grid-cols-2 gap-4 text-center">
                                        <div className="bg-slate-800/50 p-4 rounded-lg">
                                            <p className="text-xs text-slate-400">MS Share</p>
                                            <p className="text-xl font-bold mt-1 text-orange-400">
                                                {formatPct(taData.shares.MS.share_cy)}
                                            </p>
                                            <p className={`text-xs mt-1 ${getGrowthColor(taData.shares.MS.share_ppt)}`}>
                                                {formatPp(taData.shares.MS.share_ppt)} pp
                                            </p>
                                        </div>
                                        <div className="bg-slate-800/50 p-4 rounded-lg">
                                            <p className="text-xs text-slate-400">HSD Share</p>
                                            <p className="text-xl font-bold mt-1 text-cyan-400">
                                                {formatPct(taData.shares.HSD.share_cy)}
                                            </p>
                                            <p className={`text-xs mt-1 ${getGrowthColor(taData.shares.HSD.share_ppt)}`}>
                                                {formatPp(taData.shares.HSD.share_ppt)} pp
                                            </p>
                                        </div>
                                    </div>
                                </div>

                                {/* Right PPT Table */}
                                <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-lg overflow-x-auto">
                                    <h3 className="font-semibold text-slate-100 uppercase border-b border-slate-800 pb-2 mb-4">
                                        Trading Area Outlets Volume & Shares (PPT Grid)
                                    </h3>
                                    <div className="scrollable-table">
                                        <table className="w-full text-xs text-left border-collapse whitespace-nowrap">
                                            <thead className="sticky top-0 bg-slate-900 z-10">
                                                <tr className="border-b border-slate-800 text-slate-400 font-medium">
                                                    <th className="py-2 pr-4">RO Name</th>
                                                    <th className="py-2 px-3">OMC</th>
                                                    <th className="py-2 px-3 text-right">MS CY</th>
                                                    <th className="py-2 px-3 text-right">MS LY</th>
                                                    <th className="py-2 px-3 text-right">HSD CY</th>
                                                    <th className="py-2 px-3 text-right">HSD LY</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                {taData.grid.map((row, idx) => (
                                                    <tr key={idx} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                                                        <td className="py-2 pr-4 font-semibold text-slate-300 max-w-xs truncate">{row.ro}</td>
                                                        <td className="py-2 px-3 font-semibold text-slate-400">{row.omc}</td>
                                                        <td className="py-2 px-3 text-right">{formatIndian(row.ms_cy, 1)}</td>
                                                        <td className="py-2 px-3 text-right">{formatIndian(row.ms_ly, 1)}</td>
                                                        <td className="py-2 px-3 text-right">{formatIndian(row.hs_cy, 1)}</td>
                                                        <td className="py-2 px-3 text-right">{formatIndian(row.hs_ly, 1)}</td>
                                                    </tr>
                                                ))}
                                                <tr className="bg-slate-800 font-bold border-t-2 border-slate-700 sticky bottom-0">
                                                    <td className="py-2 pr-4 text-slate-100" colSpan="2">TA Total</td>
                                                    <td className="py-2 px-3 text-right">{formatIndian(taData.grid_totals.ms_cy, 1)}</td>
                                                    <td className="py-2 px-3 text-right">{formatIndian(taData.grid_totals.ms_ly, 1)}</td>
                                                    <td className="py-2 px-3 text-right">{formatIndian(taData.grid_totals.hs_cy, 1)}</td>
                                                    <td className="py-2 px-3 text-right">{formatIndian(taData.grid_totals.hs_ly, 1)}</td>
                                                </tr>
                                            </tbody>
                                        </table>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);

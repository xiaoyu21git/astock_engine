// C++数据库层的Python绑定
// 通过pybind11将C++数据库访问层暴露给Python

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/chrono.h>
#include "database/DatabaseConfig.h"
#include "database/ConnectionPool.h"
#include "database/MarketDataModels.h"
#include "database/MarketDataRepository.h"

namespace py = pybind11;
using namespace astock::database;

PYBIND11_MODULE(database_native, m) {
    m.doc() = "AStock C++ Database Layer - High Performance Market Data Storage";
    
    // ========== Enums ==========
    
    py::enum_<SymbolType>(m, "SymbolType")
        .value("STOCK", SymbolType::STOCK)
        .value("FUTURE", SymbolType::FUTURE)
        .value("ETF", SymbolType::ETF)
        .value("INDEX", SymbolType::INDEX)
        .export_values();
    
    // ========== DatabaseConfig ==========
    
    py::class_<DatabaseConfig>(m, "DatabaseConfig")
        .def(py::init<>())
        .def_readwrite("driver", &DatabaseConfig::driver)
        .def_readwrite("host", &DatabaseConfig::host)
        .def_readwrite("port", &DatabaseConfig::port)
        .def_readwrite("database", &DatabaseConfig::database)
        .def_readwrite("username", &DatabaseConfig::username)
        .def_readwrite("password", &DatabaseConfig::password)
        .def_readwrite("charset", &DatabaseConfig::charset)
        .def_readwrite("pool_size", &DatabaseConfig::pool_size)
        .def_readwrite("max_overflow", &DatabaseConfig::max_overflow)
        .def("get_connection_url", &DatabaseConfig::getConnectionUrl)
        .def("validate", &DatabaseConfig::validate);
    
    // ========== Data Models ==========
    
    py::class_<SymbolInfo>(m, "SymbolInfo")
        .def(py::init<>())
        .def_readwrite("symbol", &SymbolInfo::symbol)
        .def_readwrite("name", &SymbolInfo::name)
        .def_readwrite("symbol_type", &SymbolInfo::symbol_type)
        .def_readwrite("exchange", &SymbolInfo::exchange)
        .def_readwrite("list_date", &SymbolInfo::list_date)
        .def_readwrite("delist_date", &SymbolInfo::delist_date)
        .def_readwrite("status", &SymbolInfo::status)
        .def_readwrite("created_at", &SymbolInfo::created_at)
        .def_readwrite("updated_at", &SymbolInfo::updated_at);
    
    py::class_<DailyBar>(m, "DailyBar")
        .def(py::init<>())
        .def_readwrite("id", &DailyBar::id)
        .def_readwrite("symbol", &DailyBar::symbol)
        .def_readwrite("trade_date", &DailyBar::trade_date)
        .def_readwrite("open", &DailyBar::open)
        .def_readwrite("high", &DailyBar::high)
        .def_readwrite("low", &DailyBar::low)
        .def_readwrite("close", &DailyBar::close)
        .def_readwrite("pre_close", &DailyBar::pre_close)
        .def_readwrite("volume", &DailyBar::volume)
        .def_readwrite("turnover", &DailyBar::turnover)
        .def_readwrite("change_pct", &DailyBar::change_pct)
        .def_readwrite("amplitude", &DailyBar::amplitude)
        .def_readwrite("turnover_rate", &DailyBar::turnover_rate)
        .def_readwrite("pe_ratio", &DailyBar::pe_ratio)
        .def_readwrite("pb_ratio", &DailyBar::pb_ratio)
        .def_readwrite("market_cap", &DailyBar::market_cap)
        .def_readwrite("created_at", &DailyBar::created_at);
    
    py::class_<MinuteBar>(m, "MinuteBar")
        .def(py::init<>())
        .def_readwrite("id", &MinuteBar::id)
        .def_readwrite("symbol", &MinuteBar::symbol)
        .def_readwrite("datetime", &MinuteBar::datetime)
        .def_readwrite("frequency", &MinuteBar::frequency)
        .def_readwrite("open", &MinuteBar::open)
        .def_readwrite("high", &MinuteBar::high)
        .def_readwrite("low", &MinuteBar::low)
        .def_readwrite("close", &MinuteBar::close)
        .def_readwrite("volume", &MinuteBar::volume)
        .def_readwrite("turnover", &MinuteBar::turnover)
        .def_readwrite("created_at", &MinuteBar::created_at);
    
    py::class_<TickData>(m, "TickData")
        .def(py::init<>())
        .def_readwrite("id", &TickData::id)
        .def_readwrite("symbol", &TickData::symbol)
        .def_readwrite("datetime", &TickData::datetime)
        .def_readwrite("last_price", &TickData::last_price)
        .def_readwrite("volume", &TickData::volume)
        .def_readwrite("turnover", &TickData::turnover)
        .def_readwrite("bid_price", &TickData::bid_price)
        .def_readwrite("bid_volume", &TickData::bid_volume)
        .def_readwrite("ask_price", &TickData::ask_price)
        .def_readwrite("ask_volume", &TickData::ask_volume)
        .def_readwrite("created_at", &TickData::created_at);
    
    // ========== ConnectionPool ==========
    
    py::class_<ConnectionPool, std::shared_ptr<ConnectionPool>>(m, "ConnectionPool")
        .def(py::init<const DatabaseConfig&>())
        .def("initialize", &ConnectionPool::initialize)
        .def("shutdown", &ConnectionPool::shutdown)
        .def("get_stats", &ConnectionPool::getStats);
    
    py::class_<ConnectionPool::PoolStats>(m, "PoolStats")
        .def_readonly("total_connections", &ConnectionPool::PoolStats::total_connections)
        .def_readonly("active_connections", &ConnectionPool::PoolStats::active_connections)
        .def_readonly("idle_connections", &ConnectionPool::PoolStats::idle_connections)
        .def_readonly("failed_acquisitions", &ConnectionPool::PoolStats::failed_acquisitions)
        .def_readonly("total_acquisitions", &ConnectionPool::PoolStats::total_acquisitions);
    
    // ========== MarketDataRepository ==========
    
    py::class_<MarketDataRepository>(m, "MarketDataRepository")
        .def(py::init<std::shared_ptr<ConnectionPool>>())
        // Symbol Info
        .def("save_symbol", &MarketDataRepository::saveSymbol)
        .def("get_symbol", &MarketDataRepository::getSymbol)
        .def("get_all_symbols", &MarketDataRepository::getAllSymbols,
             py::arg("symbol_type") = std::nullopt,
             py::arg("status") = "active")
        // Daily Bar
        .def("save_daily_bars", &MarketDataRepository::saveDailyBars)
        .def("get_daily_bars", &MarketDataRepository::getDailyBars)
        .def("get_latest_bar", &MarketDataRepository::getLatestBar)
        // Minute Bar
        .def("save_minute_bars", &MarketDataRepository::saveMinuteBars)
        .def("get_minute_bars", &MarketDataRepository::getMinuteBars,
             py::arg("symbol"),
             py::arg("start_datetime"),
             py::arg("end_datetime"),
             py::arg("frequency") = 1)
        // Tick Data
        .def("save_tick_data", &MarketDataRepository::saveTickData)
        .def("get_tick_data", &MarketDataRepository::getTickData)
        // Transaction
        .def("begin_transaction", &MarketDataRepository::beginTransaction)
        .def("commit", &MarketDataRepository::commit)
        .def("rollback", &MarketDataRepository::rollback)
        .def("execute_query", &MarketDataRepository::executeQuery);
    
    // ========== Utility Functions ==========
    
    m.def("date_to_timestamp", &dateToTimestamp,
          "Convert date (year, month, day) to Unix timestamp");
    
    m.def("timestamp_to_string", &timestampToString,
          "Convert Unix timestamp to string",
          py::arg("timestamp"),
          py::arg("format") = "%Y-%m-%d");
    
    m.def("symbol_type_to_string", &symbolTypeToString,
          "Convert SymbolType enum to string");
    
    m.def("string_to_symbol_type", &stringToSymbolType,
          "Convert string to SymbolType enum");
}

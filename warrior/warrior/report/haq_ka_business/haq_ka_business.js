frappe.query_reports["Haq Ka Business"] = {
  filters: [
    // 🔍 SEARCH FIRST (most used)
    {
      fieldname: "search",
      label: "Search",
      fieldtype: "Data",
      placeholder: "Dealer / Shop / Mobile"
    },

    // 🧑‍💼 DEALER / CUSTOMER
    {
      fieldname: "customer",
      label: "Dealer",
      fieldtype: "Link",
      options: "Customer",
      get_query: () => ({
        filters: {
          customer_group: "Dealer"
        }
      })
    },

    // 🌍 LOCATION FILTERS

    // 📅 TIME SELECTION MODE
    {
      fieldname: "time_mode",
      label: "Time Filter",
      fieldtype: "Select",
      options: "Fiscal Year\nDate Range",
      default: "Fiscal Year",
      on_change: () => {
        const mode = frappe.query_report.get_filter_value("time_mode");

        if (mode === "Fiscal Year") {
          // show FY, hide dates  (NOTE: false=show, true=hide)
          frappe.query_report.toggle_filter_display("fiscal_year", false);
          frappe.query_report.toggle_filter_display("from_date", true);
          frappe.query_report.toggle_filter_display("to_date", true);
        } else {
          // show dates, hide FY
          frappe.query_report.toggle_filter_display("fiscal_year", true);
          frappe.query_report.toggle_filter_display("from_date", false);
          frappe.query_report.toggle_filter_display("to_date", false);
        }
      }

    },

    // 📆 FISCAL YEAR
    {
      fieldname: "fiscal_year",
      label: "Fiscal Year",
      fieldtype: "Link",
      options: "Fiscal Year",
      default: frappe.defaults.get_default("fiscal_year"),
      on_change: async () => {
        const fy = frappe.query_report.get_filter_value("fiscal_year");
        if (!fy) return;

        const r = await frappe.db.get_value(
          "Fiscal Year",
          fy,
          ["year_start_date", "year_end_date"]
        );

        if (r && r.message) {
          frappe.query_report.set_filter_value("from_date", r.message.year_start_date);
          frappe.query_report.set_filter_value("to_date", r.message.year_end_date);
          frappe.query_report.refresh();
        }
      }
    },

    // 📆 DATE RANGE (used only when selected)
    {
      fieldname: "from_date",
      label: "From Date",
      fieldtype: "Date",
      hidden: 1
    },
    {
      fieldname: "to_date",
      label: "To Date",
      fieldtype: "Date",
      hidden: 1
    },
    {
      fieldname: "state",
      label: "State",
      fieldtype: "Link",
      options: "Territory",
      on_change: () => {
        // clear lower-level filters
        frappe.query_report.set_filter_value("district", "");
        frappe.query_report.set_filter_value("tehsil", "");
      }
    },
    {
      fieldname: "district",
      label: "District",
      fieldtype: "Link",
      options: "District",
      get_query: () => {
        const state = frappe.query_report.get_filter_value("state");
        return state
          ? { filters: { state: state } }   // change fieldname if needed
          : {};
      },
      on_change: () => {
        frappe.query_report.set_filter_value("tehsil", "");
      }
    },
    {
      fieldname: "tehsil",
      label: "Tehsil",
      fieldtype: "Link",
      options: "Tahshil",
      get_query: () => {
        const district = frappe.query_report.get_filter_value("district");
        return district
          ? { filters: { district: district } } // change fieldname if needed
          : {};
      }
    },

    // 👁 VIEW MODE
    {
      fieldname: "view",
      label: "View",
      fieldtype: "Select",
      options: "Customer-wise\nOrder-wise",
      default: "Customer-wise"
    },
    {
      fieldname: "only_with_target",
      label: "Only With Target",
      fieldtype: "Check",
      default: 1
    },

    // 📊 CHART CONTROL
    {
      fieldname: "top_n",
      label: "Top Dealers (Chart)",
      fieldtype: "Int",
      default: 10
    }
  ],

  onload: function () {
    const mode = frappe.query_report.get_filter_value("time_mode") || "Fiscal Year";

    if (mode === "Fiscal Year") {
      frappe.query_report.toggle_filter_display("fiscal_year", false);
      frappe.query_report.toggle_filter_display("from_date", true);
      frappe.query_report.toggle_filter_display("to_date", true);
    } else {
      frappe.query_report.toggle_filter_display("fiscal_year", true);
      frappe.query_report.toggle_filter_display("from_date", false);
      frappe.query_report.toggle_filter_display("to_date", false);
    }
  }


};

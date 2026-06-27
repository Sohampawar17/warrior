frappe.pages['indian-post-payment-'].on_page_load = function (wrapper) {
  const app_page = frappe.ui.make_app_page({
    parent: wrapper,
    title: 'Indian Post Payment Collection',
    single_column: true
  });

  const $main = $(wrapper).find('.layout-main-section');
  $main.empty();

  $main.append(`
    <style>
      .ippc-wrap { max-width: 980px; margin: 0 auto; }
      .ippc-hero {
        background: linear-gradient(135deg, #f7f4ef 0%, #f1f7f4 100%);
        border: 1px solid #e6e2dc;
        border-radius: 16px;
        padding: 20px 22px;
      }
      .ippc-title { font-size: 20px; font-weight: 600; color: #2b2f36; }
      .ippc-sub { color: #5d646d; margin-top: 4px; }
      .ippc-grid { display: grid; gap: 16px; margin-top: 16px; }
      .ippc-card {
        border: 1px solid #e7e7e7;
        border-radius: 12px;
        padding: 16px;
        background: #fff;
      }
      .ippc-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 12px;
        background: #f5f5f5;
        color: #505761;
      }
      .ippc-kpi { display: flex; gap: 12px; margin-top: 10px; flex-wrap: wrap; }
      .ippc-kpi .kpi {
        background: #f9fafb;
        border: 1px solid #eef0f2;
        border-radius: 10px;
        padding: 8px 12px;
        min-width: 110px;
      }
      .ippc-kpi .kpi b { display: block; font-size: 16px; color: #1f2933; }
      .ippc-kpi .kpi span { color: #6b7280; font-size: 12px; }
      .ippc-log {
        max-height: 500px;
        overflow-y: auto;
        background: #f8fafc;
        border-radius: 14px;
        padding: 14px;
        font-size: 13px;
        border: 1px solid #e5e7eb;
      }

      .ippc-log::-webkit-scrollbar {
        width: 6px;
      }

      .ippc-log::-webkit-scrollbar-thumb {
        background: #cbd5e1;
        border-radius: 20px;
      }

      /* -------------------------------- */
      /* LOG CARD */
      /* -------------------------------- */

      .ippc-log .log-item {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        padding: 14px;
        border-radius: 12px;
        margin-bottom: 12px;
        border: 1px solid transparent;
        background: #ffffff;
      }

      .ippc-log .log-item.success {
        border-color: #d1fae5;
        background: #f0fdf4;
      }

      .ippc-log .log-item.fail {
        border-color: #fee2e2;
        background: #fef2f2;
      }

      /* -------------------------------- */
      /* BADGE */
      /* -------------------------------- */

      .ippc-log .log-badge {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        border-radius: 50%;
        font-size: 13px;
        font-weight: 700;
        flex-shrink: 0;
        color: white;
      }

      .ippc-log .log-badge.success {
        background: #16a34a;
      }

      .ippc-log .log-badge.fail {
        background: #dc2626;
      }

      /* -------------------------------- */
      /* TEXT */
      /* -------------------------------- */

      .ippc-log .log-text {
        flex: 1;
        line-height: 1.6;
        font-size: 13px;
        color: #111827;
        word-break: break-word;
      }

      /* -------------------------------- */
      /* MAIN TITLE */
      /* -------------------------------- */

      .log-main {
        font-size: 14px;
        font-weight: 700;
        margin-bottom: 12px;
        color: #111827;
      }

      /* -------------------------------- */
      /* ROWS */
      /* -------------------------------- */

      .log-row {
        display: flex;
        align-items: flex-start;
        gap: 12px;
        margin-bottom: 8px;
        padding-bottom: 6px;
        border-bottom: 1px dashed #e5e7eb;
      }

      .log-row:last-child {
        border-bottom: none;
        margin-bottom: 0;
        padding-bottom: 0;
      }

      /* -------------------------------- */
      /* LABEL */
      /* -------------------------------- */

      .log-label {
        min-width: 130px;
        font-weight: 600;
        color: #374151;
      }

      /* -------------------------------- */
      /* VALUE */
      /* -------------------------------- */

      .log-value {
        flex: 1;
        color: #111827;
        word-break: break-word;
      }
      .ippc-table {
        width: 100%;
        border-collapse: collapse;
        margin-top: 8px;
        font-size: 13px;
      }
      .ippc-table th, .ippc-table td { border: 1px solid #ececec; padding: 8px; }
      .ippc-muted { color: #6b7280; }
      @media (min-width: 900px) {
        .ippc-grid { grid-template-columns: 1.2fr 1fr; }
      }
    </style>

    <div class="ippc-wrap">
      <div class="ippc-hero">
        <div class="ippc-title">Batch Payment Entry from India Post</div>
        <div class="ippc-sub">
          Upload an Excel/CSV file and we will create Payment Entries exactly like the
          Sales Invoice “Make Payment Entry” flow.
        </div>
        <div class="ippc-kpi">
          <div class="kpi"><b id="ippc-created">0</b><span>Created</span></div>
          <div class="kpi"><b id="ippc-failed">0</b><span>Failed</span></div>
          <div class="kpi"><b id="ippc-file">-</b><span>Last File</span></div>
        </div>
      </div>

      <div class="ippc-grid">
        <div class="ippc-card">
          <div class="ippc-badge">Required Columns</div>
          <table class="ippc-table">
            <thead>
              <tr>
                <th>Column</th>
                <th>Meaning</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td><b>Article Number</b></td>
                <td>Tracking ID</td>
              </tr>
              <tr>
                <td><b>Net Amount</b></td>
                <td>Paid Amount</td>
              </tr>
            </tbody>
          </table>
          <div class="ippc-muted" style="margin-top:10px;">
            Accepted formats: .xlsx, .xls, .csv
          </div>
        </div>

        <div class="ippc-card">
          <div class="ippc-badge">Processing Log</div>
          <div id="ippc-log" class="ippc-log" style="margin-top:10px;">
            Upload a file to see results.
          </div>
        </div>
      </div>
    </div>
  `);

  const set_kpis = (res, file) => {
    $('#ippc-created').text(res.created || 0);
    $('#ippc-failed').text(res.failed || 0);
    $('#ippc-file').text(file || '-');
  };

  const set_log = (lines) => {
    const $log = $('#ippc-log');
    $log.empty();

    if (!lines || !lines.length) {
      $log.append('<div class="ippc-muted">No log entries.</div>');
      return;
    }

    lines.forEach((line) => {

	const is_success = line.includes('Success');
	const is_fail = line.includes('Failed');

	const cls = is_success
		? 'success'
		: is_fail
		? 'fail'
		: '';

	const badge = is_success
		? '✓'
		: is_fail
		? '✕'
		: '•';

	// ---------------------------------
	// Convert text into key/value pairs
	// ---------------------------------

	let formatted_html = '';

	const parts = line.split('|');

	parts.forEach(part => {

		part = part.trim();

		if (part.includes(':')) {

			let [label, value] = part.split(':');

			formatted_html += `
				<div class="log-row">
					<div class="log-label">
						${frappe.utils.escape_html(label)}
					</div>

					<div class="log-value">
						${frappe.utils.escape_html(value)}
					</div>
				</div>
			`;

		} else {

			formatted_html += `
				<div class="log-main">
					${frappe.utils.escape_html(part)}
				</div>
			`;
		}
	});

	$log.append(`

		<div class="log-item ${cls}">

			<div class="log-badge ${cls}">
				${badge}
			</div>

			<div class="log-text">
				${formatted_html}
			</div>

		</div>

	`);
});
  };

  app_page.set_secondary_action('Clear Results', () => {
    set_kpis({}, null);
    set_log([]);
  });

  // Works on older/newer Frappe
  app_page.set_primary_action('Upload File', () => {
    new frappe.ui.FileUploader({
      as_dataurl: false,
      allow_multiple: false,
      restrictions: { allowed_file_types: ['.xlsx', '.xls', '.csv'] },

      on_success(file) {
        frappe.call({
          method: "warrior.public.indian_post_payment_collection.start_payment_entries_from_excel",
          args: { file_url: file.file_url },
          freeze: true,
          freeze_message: __("Queueing payments...")
        }).then(r => {
          const job = r.message || {};
          set_kpis({}, file.file_name || file.file_url);
          set_log([`Queued | Job ID: ${job.job_id || ""}`]);
          poll_job(job.job_id, file.file_name || file.file_url);
        });
      }
    });
  });

  const poll_job = (job_id, file_name) => {
    if (!job_id) {
      set_log(["Failed | Error: Job ID was not returned."]);
      return;
    }

    const poll = () => {
      frappe.call({
        method: "warrior.public.indian_post_payment_collection.get_payment_entries_job_status",
        args: { job_id }
      }).then(r => {
        const res = r.message || {};
        set_kpis(res, file_name);
        set_log(res.log || []);

        if (["queued", "processing"].includes(res.status)) {
          setTimeout(poll, 2000);
        }
      }).catch(() => {
        set_log(["Failed | Error: Could not fetch job status."]);
      });
    };

    poll();
  };
};

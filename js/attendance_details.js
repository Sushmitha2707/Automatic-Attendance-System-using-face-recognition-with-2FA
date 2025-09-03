$(document).ready(function() {
    // Update sections when branch changes
    $('#branch').change(function() {
        $.getJSON('/get_sections/' + $(this).val(), function(data) {
            let section = $('#section');
            section.empty();
            section.append('<option value="">Select Section</option>');
            data.sections.forEach(value => {
                section.append(`<option value="${value}">${value}</option>`);
            });
        });
    });

    // Set default date to today
    $('#date').val(new Date().toISOString().split('T')[0]);

    // Update semesters
    function updateSemesters() {
        $.getJSON('/get_semesters', function(data) {
            let semester = $('#semester');
            semester.empty();
            semester.append('<option value="">Select Semester</option>');
            data.semesters.forEach(value => {
                semester.append(`<option value="${value}">${value}</option>`);
            });
        });
    }

    // View attendance button click handler
    $('#viewAttendance').click(function() {
        let branch = $('#branch').val();
        let section = $('#section').val();
        let semester = $('#semester').val();
        let date = $('#date').val();

        if (!branch || !section || !semester || !date) {
            alert('Please select all fields');
            return;
        }

        $.getJSON('/get_attendance', {
            branch: branch,
            section: section,
            semester: semester,
            date: date
        }, function(response) {
            let tbody = $('#attendanceTable tbody');
            tbody.empty();

            if (response.success) {
                response.attendance.forEach(record => {
                    tbody.append(`
                        <tr>
                            <td>${record.usn}</td>
                            <td>${record.name}</td>
                            <td>${record.time}</td>
                            <td>Present</td>
                        </tr>
                    `);
                });

                if (response.attendance.length === 0) {
                    tbody.append('<tr><td colspan="4">No attendance records found</td></tr>');
                }
            } else {
                tbody.append('<tr><td colspan="4">Error loading attendance data</td></tr>');
            }
        });
    });

    // Initialize semesters on page load
    updateSemesters();
});
// Add after existing code
function exportToCSV() {
    let branch = $('#branch').val();
    let section = $('#section').val();
    let semester = $('#semester').val();
    let date = $('#date').val();

    window.location.href = `/export_attendance?branch=${branch}&section=${section}&semester=${semester}&date=${date}&format=csv`;
}

function exportToExcel() {
    let branch = $('#branch').val();
    let section = $('#section').val();
    let semester = $('#semester').val();
    let date = $('#date').val();

    window.location.href = `/export_attendance?branch=${branch}&section=${section}&semester=${semester}&date=${date}&format=excel`;
}

$('#exportCSV').click(exportToCSV);
$('#exportExcel').click(exportToExcel);
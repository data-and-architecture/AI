-- ============================================================
-- Employee Data AI Agent
-- Sample Data
-- ============================================================

-- ============================================================
-- Departments
-- ============================================================
INSERT INTO departments
(
    department_id,
    department_code,
    department_name,
    location
)
VALUES
(1, 'ENG', 'Engineering', 'Riyadh'),
(2, 'FIN', 'Finance', 'Riyadh'),
(3, 'HR', 'Human Resources', 'Jeddah'),
(4, 'SAL', 'Sales', 'Riyadh'),
(5, 'MKT', 'Marketing', 'Jeddah')
ON CONFLICT (department_id) DO NOTHING;

-- ============================================================
-- Employees
-- ============================================================
INSERT INTO employees
(
    employee_id,
    employee_number,
    first_name,
    last_name,
    email,
    job_title,
    department_id,
    hire_date,
    salary,
    employment_status
)
VALUES
(101, 'E001', 'Ahmed',  'Ali',    'ahmed@example.com',  'Software Engineer',        1, '2022-01-15', 18000, 'ACTIVE'),
(102, 'E002', 'Sara',   'Khalid', 'sara@example.com',   'Senior Software Engineer', 1, '2020-05-10', 24000, 'ACTIVE'),
(103, 'E003', 'Omar',   'Hassan', 'omar@example.com',   'Finance Analyst',          2, '2023-02-01', 15000, 'ACTIVE'),
(104, 'E004', 'Mona',   'Salem',  'mona@example.com',   'HR Specialist',            3, '2021-08-20', 16000, 'ACTIVE'),
(105, 'E005', 'Khalid', 'Nasser', 'khalid@example.com', 'Sales Manager',            4, '2019-03-11', 26000, 'ACTIVE'),
(106, 'E006', 'Nora',   'Saeed',  'nora@example.com',   'Marketing Specialist',     5, '2024-01-08', 14000, 'ACTIVE'),
(107, 'E007', 'Faisal', 'Ahmed',  'faisal@example.com', 'Data Engineer',            1, '2023-06-12', 21000, 'ACTIVE'),
(108, 'E008', 'Layla',  'Omar',   'layla@example.com',  'Financial Analyst',        2, '2024-02-18', 15500, 'ACTIVE'),
(109, 'E009', 'Yousef', 'Hadi',   'yousef@example.com', 'Recruiter',                3, '2022-09-01', 14500, 'ACTIVE'),
(110, 'E010', 'Huda',   'Saleh',  'huda@example.com',   'Sales Representative',     4, '2024-03-20', 13000, 'ACTIVE'),
(111, 'E011', 'Majed',  'Fahad',  'majed@example.com',  'Marketing Analyst',        5, '2023-11-10', 15000, 'ACTIVE'),
(112, 'E012', 'Rania',  'Nabil',  'rania@example.com',  'Software Engineer',        1, '2025-01-13', 19000, 'ACTIVE');

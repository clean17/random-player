const toFloat = (v) => {
    if (v === null || v === undefined || v === "") return null;
    v = v.replace(/,/g, "");
    const num = parseFloat(v);         // parseFloat: 문자열을 숫자로 변환.. "42px" > 42
    return Number.isFinite(num) ? num : null;   // 유한한 숫자인지 확인.. NaN, Infinity, -Infinity는 걸러져서 null 반환
};

const test_value = '7,100';
const formatted_value = toFloat(test_value);
console.log('formatted_value', formatted_value);
function pnlAlert() {
  try {
    const response = UrlFetchApp.fetch('https://data-api.polymarket.com/positions?user={WALLET}');
    const positions = JSON.parse(response.getContentText());
    
    // ✅ ПРОВЕРКА: если нет позиций
    if (!positions || !Array.isArray(positions) || positions.length === 0) {
      console.log('Нет открытых позиций');
      return;
    }
    
    const abovePositions = positions.filter(p => 
      p.title && p.title.toLowerCase().includes('above')
    );
    const hitPositions = positions.filter(p => 
      p.title && (p.title.toLowerCase().includes('reach') || p.title.toLowerCase().includes('dip'))
    );
    
    const abovePnl = weightedPnl(abovePositions);
    const hitPnl = weightedPnl(hitPositions);
    
    if (abovePnl < -10) sendTelegram(`📉 ABOVE: ${abovePnl.toFixed(2)}%`);
    if (hitPnl < -10) sendTelegram(`📉 HIT: ${hitPnl.toFixed(2)}%`);
    
    console.log(`ABOVE: ${abovePnl.toFixed(2)}% | HIT: ${hitPnl.toFixed(2)}%`);
  } catch (error) {
    console.log('Ошибка:', error.toString());
  }
}

function weightedPnl(positions) {
  // ✅ ИСПРАВЛЕНО: проверка на undefined/null/пустой массив
  if (!positions || !Array.isArray(positions) || positions.length === 0) {
    return 0;
  }
  
  const totalPnlValue = positions.reduce((sum, p) => {
    const size = p.tokensHeld || p.amount || p.tokens || 1;
    return sum + (p.percentPnl || 0) * size;
  }, 0);
  
  const totalSize = positions.reduce((sum, p) => {
    return sum + (p.tokensHeld || p.amount || p.tokens || 1);
  }, 0);
  
  return totalPnlValue / totalSize;
}

function sendTelegram(msg) {
  const token = PropertiesService.getScriptProperties().getProperty('TG_TOKEN');
  const chatId = PropertiesService.getScriptProperties().getProperty('TG_CHAT_ID');
  if (!msg?.trim()) return;
  UrlFetchApp.fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    payload: JSON.stringify({ chat_id: chatId, text: msg }), muteHttpExceptions: true
  });
}
